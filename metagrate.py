#!/usr/bin/env python

import pandas as pd
from pathlib import Path
from argparse import ArgumentParser
# import mcol

from mlog import setup_logger
logger = setup_logger('metagrate')

C_LONGCODE = 'Long code'
C_SHORTCODE = 'Code'
C_COMPOUNDCODE = 'Compound code'
C_SMILES = 'Smiles'

CURATOR_TAG_CATEGORIES = ['Other', 'Forum', 'Series']
SITE_TAG_TYPES = ['ConformerSites', 'CanonSites', 'CrystalformSites', 'Crystalforms', 'Quatassemblies']

def parse_args():

    parser = ArgumentParser(prog='metagrate', description='Metadata migrate: Copy tags from one Fragalysis metadata.csv to another one, matching observations using their longcodes but transferring other tags')

    parser.add_argument("source", help='metadata.csv from which you want to copy information')
    parser.add_argument("template", help='metadata.csv from a download of the Fragalysis instance you wish to modify')
    parser.add_argument("-o","--output", help='Name for the output file')

    return parser.parse_args()

def load_csv(path):
	df = pd.read_csv(path)

	if 'Pose' not in df.columns:
		logger.warning(f'Old metadata format: {path}')

	# print(df.columns)

	return df

def match_row_to_source(row, source):

	longcode = row[C_LONGCODE]

	# get by longcode
	matching = source[source[C_LONGCODE] == longcode]

	# old format of longcode
	if not len(matching):
		# A71EV2A-x0450_A_201_v1 --> A71EV2A-x0450_A_201_1_A71EV2A-x0526+A+147+1
		if longcode[-2] == 'v':
			longcode = longcode.replace(f'v{longcode[-1]}', longcode[-1])
		matching = source[source[C_LONGCODE].str.startswith(longcode)]
	
	assert len(matching) == 1

	# get first match
	for i,row in matching.iterrows():
		reference = row
		break

	# checks
	assert reference[C_COMPOUNDCODE] == row[C_COMPOUNDCODE], (reference[C_COMPOUNDCODE], row[C_COMPOUNDCODE])
	assert reference[C_SMILES] == row[C_SMILES], (reference[C_SMILES], row[C_SMILES])

	return reference

def get_curator_tags(row):

	tags = []

	for col in row.index:
		if col.startswith('[') and col.split(']')[0][1:] in CURATOR_TAG_CATEGORIES:
			tags.append((col, row[col]))

	return tags

def compare_site_tags(source, template):

	for site_type in SITE_TAG_TYPES:

		logger.var(site_type, (source[site_type], template[site_type]))

def migrate_tags(source, template):

	df = template.copy()

	# df = template

	curator_tags = {}

	for i,row in df.iterrows():

		logger.debug((row[C_SHORTCODE], row[C_LONGCODE]))

		reference = match_row_to_source(row, source)

		# check XCA tags

		# curator tags:
		tags = get_curator_tags(reference)
		for col, value in tags:
			if col not in curator_tags:
				curator_tags[col] = []
			curator_tags[col].append(value)

	# apply curator tags
	for col, values in curator_tags.items():
		df[col] = values

	return df

def main():

	args = parse_args()

	output = Path(args.output or "metadata_migrated.csv").resolve()
	source = Path(args.source).resolve()
	template = Path(args.template).resolve()

	logger.var("source", source, dict(color='file'))
	logger.var("template", template, dict(color='file'))
	logger.var("output", output, dict(color='file'))

	df1 = load_csv(source)
	df2 = load_csv(template)

	df3 = migrate_tags(df1, df2)

	logger.writing(output)
	df3.to_csv(output, index=False)

if __name__ == '__main__':
	main()