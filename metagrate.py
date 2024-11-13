#!/usr/bin/env python

import pandas as pd
from pathlib import Path

# from argparse import ArgumentParser
from fnmatch import fnmatch
from typer import Typer

app = Typer()
# import mcol

from mlog import setup_logger

DEBUG = False

logger = setup_logger("metagrate")

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

CURATOR_TAGS = None

SITE_TAG_CACHE = {k: {} for k in SITE_TAG_TYPES}


def load_csv(path):

    if path.name.endswith(".xlsx"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    if "Pose" not in df.columns:
        logger.warning(f"Old metadata format: {path}")

    return df


def match_row_to_source(row, source):

    longcode = row[C_LONGCODE]

    # get by longcode
    matching = source[source[C_LONGCODE] == longcode]

    # old format of longcode
    if not len(matching):
        # A71EV2A-x0450_A_201_v1 --> A71EV2A-x0450_A_201_1_A71EV2A-x0526+A+147+1
        if longcode[-2] == "v":
            longcode = longcode.replace(f"v{longcode[-1]}", longcode[-1])
        matching = source[source[C_LONGCODE].str.startswith(longcode)]

    match len(matching):
        case 1:
            ...
        case 0:
            logger.warning(f'No observations in source w/ "{C_LONGCODE}"="{longcode}"')
            return None
            # raise ValueError(f"No observations in source w/ \"{C_LONGCODE}\"=\"{longcode}\"")
        case _:
            assert (
                len(matching) == 1
            ), f'Multiple observations in source w/ "{C_LONGCODE}"="{longcode}"'

    # get first match
    for i, row in matching.iterrows():
        reference = row
        break

    # checks

    if pd.isna(reference[C_COMPOUNDCODE]):
        logger.warning(f"Null Compound code for {reference[C_SHORTCODE]} in SOURCE file")
    
    if pd.isna(row[C_COMPOUNDCODE]):
        logger.warning(f"Null Compound code for {reference[C_SHORTCODE]} in TEMPLATE file")
    
    if pd.isna(reference[C_COMPOUNDCODE]) and pd.isna(row[C_COMPOUNDCODE]): 
        pass
    elif reference[C_COMPOUNDCODE] != row[C_COMPOUNDCODE]:
        logger.var("Compound code in SOURCE", reference[C_COMPOUNDCODE])
        logger.var("Compound code in TEMPLATE", row[C_COMPOUNDCODE])
        raise ValueError(f"Compound codes in SOURCE do not match TEMPLATE for {reference[C_SHORTCODE]}")

    assert reference[C_SMILES] == row[C_SMILES], (reference[C_SMILES], row[C_SMILES])

    return reference


def get_curator_tags(row):

    tags = []

    for col in row.index:
        if col.startswith("[") and col.split("]")[0][1:] in CURATOR_TAG_CATEGORIES:
            tags.append((col, row[col]))

    global CURATOR_TAGS
    CURATOR_TAGS = tags

    return tags


def compare_site_tags(source, template):

    global SITE_TAG_CACHE

    assert source["Long code"] == template["Long code"], f'SOURCE Long code does not match TEMPLATE: {source["Long code"],template["Long code"]}. Try running with --no-rename-sites'

    for site_type in SITE_TAG_TYPES:

        cache = SITE_TAG_CACHE[site_type]

        col = f"{site_type} alias"

        source_value = remove_tag_prefix(source[col])
        template_value = remove_tag_prefix(template[col])
        cache_value = cache[template_value] if template_value in cache else None

        if cache_value and cache_value != source_value:
            logger.var(
                col,
                str(
                    dict(
                        source_value=source_value,
                        template_value=template_value,
                        cache_value=cache_value,
                    )
                ),
            )
            logger.error(f"{col} inconsistency ({source['Long code']})")
            raise ValueError(f"{col} inconsistency ({source['Long code']})!")

        elif cache_value is None:
            if DEBUG:
                logger.debug(
                    f'Caching {site_type}["{template_value}"]="{source_value}"'
                )

            # if source_value == "Glu88":
            #     raise ValueError

            cache[template_value] = source_value


def remove_tag_prefix(tag):
    return tag.split(" - ")[1]


def detect_generated_site_alias(site_type, alias):

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


def apply_generated_site_aliases(df):

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

            logger.var(f"Renamed {site_type} alias", f"{old} --> {new}")


def migrate_tags(source, template, site_tags: bool = True):

    df = template.copy()

    curator_tags = {}

    for i, row in df.iterrows():

        reference = match_row_to_source(row, source)

        if reference is not None:

            # check XCA tags
            if site_tags:
                compare_site_tags(reference, row)

            # curator tags:
            tags = get_curator_tags(reference)
        else:
            tags = CURATOR_TAGS

        for col, value in tags:
            if col not in curator_tags:
                curator_tags[col] = []
            curator_tags[col].append(value)

    # apply curator tags
    for col, values in curator_tags.items():
        df[col] = values
        logger.var("Migrated curator tag", col)

    return df


@app.command()
def migrate(
    source: str,
    template: str,
    output: str = "metadata_migrated.csv",
    rename_sites: bool = True,
    debug: bool = False,
):

    global DEBUG
    DEBUG = debug

    output = Path(output).resolve()
    source = Path(source).resolve()
    template = Path(template).resolve()

    logger.var("source", source, dict(color="file"))
    logger.var("template", template, dict(color="file"))
    logger.var("output", output, dict(color="file"))

    df1 = load_csv(source)
    df2 = load_csv(template)

    df3 = migrate_tags(df1, df2, site_tags=rename_sites)

    if rename_sites:
        apply_generated_site_aliases(df3)

    logger.writing(output)
    df3.to_csv(output, index=False)


def main():
    app()


if __name__ == "__main__":
    app()
