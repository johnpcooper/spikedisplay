import re
import os

import gzip

import pandas as pd
import numpy as np

from Bio.Seq import Seq
from Bio import SeqIO
from Bio import bgzf

import pysam

from difflib import get_close_matches

from spikedisplay import constants

def get_bam_records_list(filepath, n_records_to_get=None, *kwargs):
    records = []
    i=0
    with pysam.AlignmentFile(filepath, 'r') as file:
        for record in file:
            records.append(record)
            if n_records_to_get == None:
                pass
            else:
                if i == n_records_to_get:
                    break
                else:
                    pass
            i+=1
    return records

def get_records_df(directory, reads_fn=None, get_n_records=None, **kwargs):
    """
    Look in <directory> for <reads_fn>. Read the file in with
    gzip.open and parse each record using the Bio (biopython) 
    module SeqIO to parse the file as 'fastq' by default
    
    Return a dataframe of that records file with various identifying
    information
    """
    return_records_list = kwargs.get('return_records_list', True)
    
    file_path = os.path.join(directory, reads_fn)
    
    if os.path.exists(directory):
        print(f'Found directory at {directory}')
        if os.path.exists(file_path):
            print(f'Found file at {file_path}')
        else:
            print(f'No file at {file_path}')
            return None
    else:
        print(f'No directory at {directory}')
        return None
    
    records = []
    identifiers = []
    sequences = []
    lengths = []
    i=0
    with gzip.open(os.path.join(directory, reads_fn), 'rt') as file:
        for record in SeqIO.parse(file, "fastq"):
            records.append(record)
            identifiers.append(record.id)
            sequences.append(str(record.seq))
            lengths.append(len(str(record.seq)))
            if get_n_records != None:
                pass
            else:
                if i == get_n_records:
                    break
                else:
                    pass
            i+=1

    df_dict = {
        'id': identifiers,
        'sequence': sequences,
        'length': lengths
        }
    df = pd.DataFrame(df_dict)
    df.loc[:, 'source_file_path'] = file_path
    
    if return_records_list:
        return records, df
    else:
        return df

def get_mismatch_indices(a, b, print_output=False):
    if len(a)==len(b):
        mismatch_indices = [i for i in range(len(a)) if a[i] != b[i]]
        if print_output:
            print(f'Found {len(mismatch_indices)} mismatch between strings', end="\r")
        else:
            pass
        return mismatch_indices
    else:
        return None


def floats_to_ints(df, inplace=True, **kwargs):
    """
    For all columns in <df> that contain values of type
    np.float64, change them to integer inplace by default.
    
    You can also specify which columns to change in kwargs
    using kwarg 'columns'
    """
    columns = kwargs.get('columns', df.columns)
    if inplace:
        # this means that df_final and df will refer
        # to the same object in the namespace. 
        df_final = df
    else:
        df_final = df.copy()
    for col in columns:
        coltype = type(df_final[col].iloc[0])
        if coltype == np.float64:
    #         print(f'{col} contains floats')
            df_final.loc[:, col] = df_final.loc[:, col].astype(int)
        else:
            pass
    if not inplace:
        return df_final


def label_variant_name(df):
    """
    Annotate variant name, e.g. 'G72D', using information already
    annotated in the dataframe
    """
    df.loc[:, 'mismatch_site_in_full_length_wt_seq'] = df.mismatch_index_in_full_length_wt_seq + 1
    wtaa_site = df.wt_aa_at_mismatch.str.cat(df.mismatch_site_in_full_length_wt_seq.map(str))
    df.loc[:, 'variant_name'] = wtaa_site
    wtaa_site_mutantaa = df.variant_name.str.cat(df.mutant_aa.map(str))
    df.loc[:, 'variant_name'] = wtaa_site_mutantaa
    if 'library_name' in list(df.columns):
        newcol = df.sample_name.str.cat(df.library_name, sep='-')
        df.loc[:, 'sample_library'] = newcol

def create_all_bam_df(output_dir):
    dfs = []
    filenames = [fn for fn in os.listdir(output_dir) if 'bam.csv.gz' in fn]
    for filename in filenames:
        print(f'{filename}')
        df = pd.read_csv(os.path.join(output_dir, filename), compression='gzip')
        df.loc[:, 'source_file'] = filename
        df.loc[:, 'sample_name'] = filename.split('-')[0]
        df.loc[:, 'library_name'] = filename.split('-')[1][0:4]
        # To keep things moving quickly, we will change every number
        # possible into an integer instead of float. This means we 
        # have to get rid of np.nan vals since these are float.
        # Since -1 has no meaning in these data (but anything >=0
        # potentially could), we're replacing nan with -1 and 
        # integrizing numeric columns
        df.fillna(-1, inplace=True)
        floats_to_ints(df)
        # Get rid of stop codon mutants
        df = df[df.mutant_aa!='*']
        label_variant_name(df)
        dfs.append(df)
    all_bam_df = pd.concat(dfs, ignore_index=True)
    return all_bam_df, dfs


def assign_bin_from_barcode(record, record_type='fastq', **kwargs):
    
    barcode_index = kwargs.get('barcode_index', constants.rbd_barcode_index)
    
    if record_type=='fastq':
        identifier =  record.id
    elif record_type=='bam':
        identifier = record.query_name
    else:
        pass
        
    match = re.search(constants.patterns.barcode, identifier)
    if match:
        if len(match.groups()) == 2:
            # Then we should have detected a forward and 
            # a reverse barcode in the sequence identifier
            pass
        else:
            # print(f'Only found {len(match.groups())} barcodes')
            return 0, 'None', 'None'
    else:
        # print(f'No barcodes found')
        return 0, 'None', 'None'
    
    bc1 = match.groups()[0]
    bc2 = match.groups()[1]
    bc1rc = str(Seq(bc1).reverse_complement())
    bc2rc = str(Seq(bc2).reverse_complement())

    barcode_candidates = [bc1, bc2, bc1rc, bc2rc]
    closest_matches = []
    bin_number = 0
    fwd_barcode = 'None'
    rev_barcode = 'None'
    for cand in barcode_candidates:
        close_matches = get_close_matches(cand, barcode_index.sequence)
        if len(close_matches) > 0:
            closest_match = close_matches[0]
            closest_matches.append(closest_match)
            bin_number_check = barcode_index.set_index('sequence').loc[closest_match, 'bin_number']
            if not np.isnan(bin_number_check):
                bin_number = bin_number_check
                fwd_barcode = closest_match
            else:
                rev_barcode = closest_match

    return int(bin_number), fwd_barcode, rev_barcode
    