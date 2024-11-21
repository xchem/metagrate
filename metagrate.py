#!/usr/bin/env python

import mrich
import pandas as pd
from typer import Typer
from pathlib import Path
from fnmatch import fnmatch

app = Typer()

DEBUG = False

# specify some fragalysis
C_LONGCODE = "Long code"
C_SHORTCODE = "Code"
C_COMPOUNDCODE = "Compound code"
C_SMILES = "Smiles"
CURATOR_TAG_CATEGORIES = ["Other", "Forum", "Series"]
SITE_TAG_TYPES = [
    "ConformerSites",
    "CanonSites",
    "CrystalformSites",
    "Crystalforms",
    "Quatassemblies",
]


# cache some tag info in a dictionary for self-consistency checks
CURATOR_TAGS = None
SITE_TAG_CACHE = {k: {} for k in SITE_TAG_TYPES}


def load_csv(path: Path) -> pd.DataFrame:
    """load a CSV/XLSX into a dataframe

    :param path: `Path` to input file
    """

    if path.name.endswith(".xlsx"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    if "Pose" not in df.columns:
        mrich.warning(f"Old metadata format: {path}")

    return df


def match_row_to_source(template_row: pd.Series, source: pd.DataFrame) -> pd.Series:
    """
    :param template_row: `DataFrame` row in TEMPLATE to match to SOURCE
    :param template_row: SOURCE `DataFrame` to search
    :returns: `source` entry that matches `template_row`
    """

    template_longcode = template_row[C_LONGCODE]

    # get by exact longcode match
    matching_rows = source[source[C_LONGCODE] == template_longcode]

    # try updating from old format of longcode
    if not len(matching_rows):

        # A71EV2A-x0450_A_201_v1 --> A71EV2A-x0450_A_201_1_A71EV2A-x0526+A+147+1

        # change suffix _v1 -> _1
        if template_longcode[-2] == "v":
            template_longcode = template_longcode.replace(
                f"v{template_longcode[-1]}", template_longcode[-1]
            )

        # try prefix matching
        matching_rows = source[source[C_LONGCODE].str.startswith(template_longcode)]

    match len(matching_rows):
        case 1:
            # single match is ok
            source_row = matching_rows.iloc[0]
        case 0:
            # no matches prints a warning
            mrich.warning(
                f"No observations in source w/ {C_LONGCODE}: {template_longcode}"
            )
            return None
        case _:
            # ambiguous match throws an error
            raise ValueError(
                f'Multiple observations in source w/ "{C_LONGCODE}"="{template_longcode}"'
            )

    # check that the compound codes match

    if pd.isna(source_row[C_COMPOUNDCODE]):
        mrich.warning(
            f"Null Compound code for {source_row[C_SHORTCODE]} in SOURCE file"
        )

    if pd.isna(template_row[C_COMPOUNDCODE]):
        mrich.warning(
            f"Null Compound code for {source_row[C_SHORTCODE]} in TEMPLATE file"
        )

    if pd.isna(source_row[C_COMPOUNDCODE]) and pd.isna(template_row[C_COMPOUNDCODE]):
        pass
    elif source_row[C_COMPOUNDCODE] != template_row[C_COMPOUNDCODE]:
        mrich.var("Compound code in SOURCE", source_row[C_COMPOUNDCODE])
        mrich.var("Compound code in TEMPLATE", template_row[C_COMPOUNDCODE])
        raise ValueError(
            f"Compound codes in SOURCE do not match TEMPLATE for {source_row[C_SHORTCODE]}"
        )

    # check that the smiles match
    if source_row[C_SMILES] != template_row[C_SMILES]:
        mrich.var("SMILES in SOURCE", source_row[C_SMILES])
        mrich.var("SMILES in TEMPLATE", template_row[C_SMILES])
        raise ValueError(
            f"SMILES in SOURCE do not match TEMPLATE for {source_row[C_SHORTCODE]}"
        )

    return source_row


def get_curator_tags(row: pd.Series) -> list[str]:
    """Extract non-XCA tags from a metadata row and sets the CURATOR_TAGS global variable

    Identify tags in the syntax: "[TYPE] TAG", where TYPE must be in CURATOR_TAG_CATEGORIES

    :param row: row to extract from
    :returns: list of string tags
    """

    tags = []
    for col in row.index:
        if col.startswith("[") and col.split("]")[0][1:] in CURATOR_TAG_CATEGORIES:
            tags.append((col, row[col]))

    global CURATOR_TAGS
    CURATOR_TAGS = tags

    return tags


def compare_site_tags(source_row: pd.Series, template_row: pd.Series) -> None:
    """Compare all XCA-generated site tags between the two metadata rows, and all previously seen values in the SITE_TAG_CACHE.

    :raises: ValueError in the event of inconsistencies

    """

    global SITE_TAG_CACHE

    ## assert the longcodes are the same
    if source_row["Long code"] != template_row["Long code"]:
        raise ValueError(
            f'SOURCE_row Long code does not match template_row: {source_row["Long code"],template_row["Long code"]}. Try running with --no-rename-sites'
        )

    for site_type in SITE_TAG_TYPES:

        cache = SITE_TAG_CACHE[site_type]

        col = f"{site_type} alias"

        source_value = remove_tag_prefix(source_row[col])
        template_value = remove_tag_prefix(template_row[col])
        cache_value = cache[template_value] if template_value in cache else None

        # Cache value differs from source_value
        if cache_value and cache_value != source_value:
            mrich.var(
                col,
                str(
                    dict(
                        source_value=source_value,
                        template_value=template_value,
                        cache_value=cache_value,
                    )
                ),
            )
            mrich.error(f"{col} inconsistency ({source_row['Long code']})")
            raise ValueError(f"{col} inconsistency ({source_row['Long code']})!")

        # store value in cache
        elif cache_value is None:
            if DEBUG:
                mrich.debug(f'Caching {site_type}["{template_value}"]="{source_value}"')

            cache[template_value] = source_value


def remove_tag_prefix(tag: str) -> str:
    """Remove prefix from tag: e.g. '1 - Site 1' --> 'Site 1'"""
    return tag.split(" - ")[1]


def detect_generated_site_alias(site_type: str, alias: str) -> bool:
    """Attempts to detect if a XCA-site tag name has been generated or assigned by a curator.

    :returns: True/False
    """

    match site_type:
        case "ConformerSites":
            if fnmatch(alias, "*-x[0-9][0-9][0-9][0-9]"):
                return True
            elif fnmatch(alias, "*[0-9][0-9][0-9][0-9]/*/*"):
                return True

        case "CanonSites":
            if fnmatch(alias, "*-x[0-9][0-9][0-9][0-9]/*/*/*"):
                return True
            elif fnmatch(alias, "*[0-9][0-9][0-9][0-9]/*/*/*"):
                return True

        case "CrystalformSites":
            if fnmatch(alias, "*-x[0-9][0-9][0-9][0-9]/*/*"):
                return True
            elif fnmatch(alias, "*[0-9][0-9][0-9][0-9]/*/*"):
                return True

        case "Crystalforms":
            if fnmatch(alias, "*_*_*"):
                return True
            elif fnmatch(alias, "*/*/*"):
                return True

        case "Quatassemblies":
            return False

        case _:
            raise NotImplementedError(f"detect_generated_site_alias({site_type=})")

    return False


def apply_generated_site_aliases(df: pd.DataFrame) -> None:
    """Rename XCA site tag names based on SITE_TAG_CACHE (in-place)"""

    del_list = []

    for site_type in SITE_TAG_CACHE:
        for old, new in SITE_TAG_CACHE[site_type].items():
            is_generated = detect_generated_site_alias(site_type, new)

            if is_generated:
                del_list.append((site_type, old))

            elif old == new:
                del_list.append((site_type, old))

    for site_type, old in del_list:
        del SITE_TAG_CACHE[site_type][old]

    for site_type in SITE_TAG_CACHE:
        for old, new in SITE_TAG_CACHE[site_type].items():

            col = f"{site_type} alias"

            subset = df[df[col].str.endswith(old)]

            prefix = subset[col].values[0].split(" - ")[0]

            df.loc[subset.index, col] = f"{prefix} - {new}"

            mrich.var(f"Renamed {site_type} alias", f"{old} --> {new}")


def migrate_tags(
    source: pd.DataFrame,
    template: pd.DataFrame,
    site_tags: bool = True,
    debug: bool = False,
) -> pd.DataFrame:

    df = template.copy()

    curator_tags = {}

    for i, row in df.iterrows():

        # try to find matching SOURCE row
        reference = match_row_to_source(row, source)

        if reference is not None:

            # check XCA tags
            if site_tags:
                compare_site_tags(reference, row)

            # curator tags:
            tags = get_curator_tags(reference)

        else:
            # leave them empty
            if debug:
                mrich.debug(f"No curator tags: {row[C_LONGCODE]}")
            continue

        for col, value in tags:
            values = curator_tags.get(col, list())
            values.append(value)
            curator_tags[col] = values

            # set the value
            df.at[i, col] = value

    from rich.table import Table

    table = Table(title="Migrated Curator Tags")
    table.add_column("Name", style="var_name")
    table.add_column("#migrated", style="result")
    table.add_column("#TRUE", style="success")

    # apply curator tags
    for col, values in curator_tags.items():

        # replace empty values
        df[col].fillna(False, inplace=True)
        trues = [v for v in values if v]
        table.add_row(col, str(len(values)), str(len(trues)))

    mrich.print(table)

    return df


@app.command()
def migrate(
    source: str,
    template: str,
    output: str = "metadata_migrated.csv",
    rename_sites: bool = True,
    debug: bool = False,
) -> None:
    """Migrate tags between versions of Fragalysis"""

    # set debug level
    global DEBUG
    DEBUG = debug

    # solve paths
    output = Path(output).resolve()
    source = Path(source).resolve()
    template = Path(template).resolve()

    # console output
    mrich.var("source", source)
    mrich.var("template", template)
    mrich.var("output", output)

    # load inputs into dataframes
    df1 = load_csv(source)
    df2 = load_csv(template)

    # perform the migration
    df3 = migrate_tags(df1, df2, site_tags=rename_sites, debug=debug)

    # apply site aliases
    if rename_sites:
        apply_generated_site_aliases(df3)

    # write output
    mrich.writing(output)
    df3.to_csv(output, index=False)


def main() -> None:
    """Run the Typer app"""
    app()


if __name__ == "__main__":
    app()
