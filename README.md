
# metagrate

> Metadata Migrate

## Usage at DLS

For use at DLS metagrate has been set up at `/dls/science/groups/i04-1/software/max/metagrate`

To use it:

1. Load the python environment

```
source /dls/science/groups/i04-1/software/max/load_py310.sh
```

2. See the (barebones) help screen:

```
$METAGRATE --help
```

3. Migrate a metadata.csv file

```
$METAGRATE SOURCE TEMPLATE --output OUTPUT
```

- `SOURCE` is the metadata.csv containing the tags you want to migrate, i.e. this file should be from a Fragalysis download of a target where you have renamed the CanonicalSites and added your own tags, etc.
- `TEMPLATE` is a metadata.csv downloaded from the working Fragalysis target you wish to move the tags to, i.e. if you have just done a fresh LHS upload and want to migrate tags from an old version of the target.
- `OUTPUT` is the optional name of the output CSV file.

**N.B. because Fragalysis names all the metadata files `metadata.csv` it is recommended you rename all your input and output files so you don't forget where they came from**

Some example files are provided in `examples/`

## Debugging common errors

### AssertionError: SOURCE Long code does not match TEMPLATE

If you see the following error, the CanonicalSites or observation longcodes between the two files are incompatible. Try running with the `--no-rename-sites` option to skip renaming the XCA sites and just migrate the "curator" tags.

```
AssertionError: SOURCE Long code does not match TEMPLATE: ('3vws_A_1004_1_3vws+A+1003+1', '3vws_A_1004_v1'). Try running 
with --no-rename-sites
```

## Installation (not at DLS)

Install the following dependencies and clone this repository:

```
pip install pandas mpytools
git clone git@github.com:xchem/metagrate
```
