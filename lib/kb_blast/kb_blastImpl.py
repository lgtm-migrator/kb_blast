#BEGIN_HEADER
import os
import sys
import shutil
import hashlib
import subprocess
import requests
import re
import traceback
import uuid
from datetime import datetime
from pprint import pprint, pformat
import numpy as np
import gzip

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio.Alphabet import generic_protein
from biokbase.workspace.client import Workspace as workspaceService
from requests_toolbelt import MultipartEncoder
from biokbase.AbstractHandle.Client import AbstractHandle as HandleService

# silence whining
import requests
requests.packages.urllib3.disable_warnings()

#END_HEADER


class kb_blast:
    '''
    Module Name:
    kb_blast

    Module Description:
    ** A KBase module: kb_blast
**
** This module contains 6 methods from BLAST+: BLASTn, BLASTp, BLASTx, tBLASTx, tBLASTn, and PSI-BLAST
**
    '''

    ######## WARNING FOR GEVENT USERS #######
    # Since asynchronous IO can lead to methods - even the same method -
    # interrupting each other, you must be *very* careful when using global
    # state. A method could easily clobber the state set by another while
    # the latter method is running.
    #########################################
    #BEGIN_CLASS_HEADER
    workspaceURL = None
    shockURL = None
    handleURL = None

    Make_BLAST_DB = '/kb/module/blast/bin/makeblastdb'
    BLASTn        = '/kb/module/blast/bin/blastn'
    BLASTp        = '/kb/module/blast/bin/blastp'
    BLASTx        = '/kb/module/blast/bin/blastx'
    tBLASTn       = '/kb/module/blast/bin/tblastn'
    tBLASTx       = '/kb/module/blast/bin/tblastx'
    psiBLAST      = '/kb/module/blast/bin/psiblast'

    # target is a list for collecting log messages
    def log(self, target, message):
        # we should do something better here...
        if target is not None:
            target.append(message)
        print(message)
        sys.stdout.flush()

    def KB_SDK_data2file_translate_nuc_to_prot_seq (self, 
                                                    nuc_seq, 
                                                    table='11'):
        if nuc_seq == None:
            raise ValueError("KB_SDK_data2file_translate_nuc_to_prot_seq() FAILURE: nuc_seq required")

        nuc_seq = nuc_seq.upper()
        prot_seq = ''
        if table != '11':
            raise ValueError ("error in translate_nuc_to_prot_seq.  Only know genetic code table 11 (value used '%s')"%table)

        genetic_code = dict()
        genetic_code['11'] = {
            'ATA':'I', 'ATC':'I', 'ATT':'I', 'ATG':'M',
            'ACA':'T', 'ACC':'T', 'ACG':'T', 'ACT':'T',
            'AAC':'N', 'AAT':'N', 'AAA':'K', 'AAG':'K',
            'AGC':'S', 'AGT':'S', 'AGA':'R', 'AGG':'R',
            'CTA':'L', 'CTC':'L', 'CTG':'L', 'CTT':'L',
            'CCA':'P', 'CCC':'P', 'CCG':'P', 'CCT':'P',
            'CAC':'H', 'CAT':'H', 'CAA':'Q', 'CAG':'Q',
            'CGA':'R', 'CGC':'R', 'CGG':'R', 'CGT':'R',
            'GTA':'V', 'GTC':'V', 'GTG':'V', 'GTT':'V',
            'GCA':'A', 'GCC':'A', 'GCG':'A', 'GCT':'A',
            'GAC':'D', 'GAT':'D', 'GAA':'E', 'GAG':'E',
            'GGA':'G', 'GGC':'G', 'GGG':'G', 'GGT':'G',
            'TCA':'S', 'TCC':'S', 'TCG':'S', 'TCT':'S',
            'TTC':'F', 'TTT':'F', 'TTA':'L', 'TTG':'L',
            'TAC':'Y', 'TAT':'Y', 'TAA':'_', 'TAG':'_',
            'TGC':'C', 'TGT':'C', 'TGA':'_', 'TGG':'W'
            }
        prot_seq = ''.join([genetic_code[table].get(nuc_seq[3*i:3*i+3],'X') for i in range(len(nuc_seq)//3)])
        return prot_seq

    def get_single_end_read_library(self, ws_data, ws_info, forward):
        pass

    def get_feature_set_seqs(self, ws_data, ws_info):
        pass

    def get_genome_feature_seqs(self, ws_data, ws_info):
        pass


    # export feature sequences to FASTA file
    #
    def KB_SDK_data2file_Genome2Fasta(self,
                                      genome_object = None,
                                      file = None,
                                      dir = None,
                                      console = [],
                                      invalid_msgs = [],
                                      residue_type = 'nuc',
                                      feature_type  = 'ALL',
                                      record_id_pattern = '%%feature_id%%',
                                      record_desc_pattern = '[%%genome_id%%]',
                                      case = 'UPPER',
                                      linewrap = None
                                      ):

        if genome_object == None:
            self.log(console,"KB_SDK_data2file_Genome2Fasta() FAILURE: genome_object required")
            raise ValueError("KB_SDK_data2file_Genome2Fasta() FAILURE: genome_object required")

        # init and clean up params
        feature_sequence_found = False
        residue_type = residue_type[0:3].lower()
        feature_type = feature_type.upper()
        case = case[0:1].upper()
        
        def record_header_sub(str, feature_id, genome_id):
            str = str.replace('%%feature_id%%', feature_id)
            str = str.replace('%%genome_id%%', genome_id)
            return str

        if file == None:
            file = 'runfile.fasta'
        if dir == None:
            dir = self.scratch
        fasta_file_path = os.path.join(dir, file)
        self.log(console, 'KB SDK data2file Genome2Fasta: writing fasta file: '+fasta_file_path)


        # FIX: should I write recs as we go to reduce memory footprint, or is a single buffer write much faster?  Check later.
        #
        #records = []
        with open(fasta_file_path, 'w', 0) as fasta_file_handle:
                        
            for feature in genome_object['features']:

                if feature_type == 'ALL' or feature_type == feature['type']:

                    # protein recs
                    if residue_type == 'pro' or residue_type == 'pep':
                        if feature['type'] != 'CDS':
                            continue
                        elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                            self.log(invalid_msgs, "bad CDS feature "+feature['id']+": No protein_translation field.")
                        else:
                            feature_sequence_found = True
                            rec_id = record_id_pattern
                            rec_desc = record_desc_pattern
                            rec_id = record_header_sub(rec_id, feature['id'], genome_object['id'])
                            rec_desc = record_header_sub(rec_desc, feature['id'], genome_object['id'])
                            seq = feature['protein_translation']
                            seq = seq.upper() if case == 'U' else seq.lower()

                            rec_rows = []
                            rec_rows.append('>'+rec_id+' '+rec_desc)
                            if linewrap == None or linewrap == 0:
                                rec_rows.append(seq)
                            else:
                                seq_len = len(seq)
                                base_rows_cnt = seq_len//linewrap
                                for i in range(base_rows_cnt):
                                    rec_rows.append(seq[i*linewrap:(i+1)*linewrap])
                                rec_rows.append(seq[base_rows_cnt*linewrap:])
                            rec = "\n".join(rec_rows)+"\n"

                            #record = SeqRecord(Seq(seq), id=rec_id, description=rec_desc)
                            #records.append(record)
                            fasta_file_handle.write(rec)

                    # nuc recs
                    else:
                        if 'dna_sequence' not in feature or feature['dna_sequence'] == None:
                            self.log(invalid_msgs, "bad feature "+feature['id']+": No dna_sequence field.")
                        else:
                            feature_sequence_found = True
                            rec_id = record_id_pattern
                            rec_desc = record_desc_pattern
                            rec_id = record_header_sub(rec_id, feature['id'], genome_object['id'])
                            rec_desc = record_header_sub(rec_desc, feature['id'], genome_object['id'])
                            seq = feature['dna_sequence']
                            seq = seq.upper() if case == 'U' else seq.lower()

                            rec_rows = []
                            rec_rows.append('>'+rec_id+' '+rec_desc)
                            if linewrap == None or linewrap == 0:
                                rec_rows.append(seq)
                            else:
                                seq_len = len(seq)
                                base_rows_cnt = seq_len//linewrap
                                for i in range(base_rows_cnt):
                                    rec_rows.append(seq[i*linewrap:(i+1)*linewrap])
                                rec_rows.append(seq[base_rows_cnt*linewrap:])
                            rec = "\n".join(rec_rows)+"\n"

                            #record = SeqRecord(Seq(seq), id=rec_id, description=rec_desc)
                            #records.append(record)
                            fasta_file_handle.write(rec)

        # report if no features found
        if not feature_sequence_found:
            self.log(invalid_msgs, "No sequence records found in Genome "+genome_object['id']+" of residue_type: "+residue_type+", feature_type: "+feature_type)
        #else:
        #    SeqIO.write(records, fasta_file_path, "fasta")


        return fasta_file_path


#    def KB_SDK_data2file_GenomeAnnotation2Fasta(self):
#        return 'HELLO KITTY'

    def get_genome_set_feature_seqs(self, ws_data, ws_info):
        pass

    # config contains contents of config file in a hash or None if it couldn't
    # be found
    def __init__(self, config):
        #BEGIN_CONSTRUCTOR
        self.workspaceURL = config['workspace-url']
        self.shockURL = config['shock-url']
        self.handleURL = config['handle-service-url']
        self.scratch = os.path.abspath(config['scratch'])
        # HACK!! temporary hack for issue where megahit fails on mac because of silent named pipe error
        #self.host_scratch = self.scratch
        self.scratch = os.path.join('/kb','module','local_scratch')
        # end hack
        if not os.path.exists(self.scratch):
            os.makedirs(self.scratch)

        #END_CONSTRUCTOR
        pass


    # Helper script borrowed from the transform service, logger removed
    #
    def upload_file_to_shock(self,
                             console,  # DEBUG
                             shock_service_url = None,
                             filePath = None,
                             ssl_verify = True,
                             token = None):
        """
        Use HTTP multi-part POST to save a file to a SHOCK instance.
        """
        self.log(console,"UPLOADING FILE "+filePath+" TO SHOCK")

        if token is None:
            raise Exception("Authentication token required!")

        #build the header
        header = dict()
        header["Authorization"] = "Oauth {0}".format(token)
        if filePath is None:
            raise Exception("No file given for upload to SHOCK!")

        dataFile = open(os.path.abspath(filePath), 'rb')
        m = MultipartEncoder(fields={'upload': (os.path.split(filePath)[-1], dataFile)})
        header['Content-Type'] = m.content_type

        #logger.info("Sending {0} to {1}".format(filePath,shock_service_url))
        try:
            response = requests.post(shock_service_url + "/node", headers=header, data=m, allow_redirects=True, verify=ssl_verify)
            dataFile.close()
        except:
            dataFile.close()
            raise
        if not response.ok:
            response.raise_for_status()
        result = response.json()
        if result['error']:
            raise Exception(result['error'][0])
        else:
            return result["data"]


    def upload_SingleEndLibrary_to_shock_and_ws (self,
                                                 ctx,
                                                 console,  # DEBUG
                                                 workspace_name,
                                                 obj_name,
                                                 file_path,
                                                 provenance,
                                                 sequencing_tech):

        self.log(console,'UPLOADING FILE '+file_path+' TO '+workspace_name+'/'+obj_name)

        # 1) upload files to shock
        token = ctx['token']
        forward_shock_file = self.upload_file_to_shock(
            console,  # DEBUG
            shock_service_url = self.shockURL,
            filePath = file_path,
            token = token
            )
        #pprint(forward_shock_file)
        self.log(console,'SHOCK UPLOAD DONE')

        # 2) create handle
        self.log(console,'GETTING HANDLE')
        hs = HandleService(url=self.handleURL, token=token)
        forward_handle = hs.persist_handle({
                                        'id' : forward_shock_file['id'], 
                                        'type' : 'shock',
                                        'url' : self.shockURL,
                                        'file_name': forward_shock_file['file']['name'],
                                        'remote_md5': forward_shock_file['file']['checksum']['md5']})

        
        # 3) save to WS
        self.log(console,'SAVING TO WORKSPACE')
        single_end_library = {
            'lib': {
                'file': {
                    'hid':forward_handle,
                    'file_name': forward_shock_file['file']['name'],
                    'id': forward_shock_file['id'],
                    'url': self.shockURL,
                    'type':'shock',
                    'remote_md5':forward_shock_file['file']['checksum']['md5']
                },
                'encoding':'UTF8',
                'type':'fasta',
                'size':forward_shock_file['file']['size']
            },
            'sequencing_tech':sequencing_tech
        }
        self.log(console,'GETTING WORKSPACE SERVICE OBJECT')
        ws = workspaceService(self.workspaceURL, token=ctx['token'])
        self.log(console,'SAVE OPERATION...')
        new_obj_info = ws.save_objects({
                        'workspace':workspace_name,
                        'objects':[
                            {
                                'type':'KBaseFile.SingleEndLibrary',
                                'data':single_end_library,
                                'name':obj_name,
                                'meta':{},
                                'provenance':provenance
                            }]
                        })
        self.log(console,'SAVED TO WORKSPACE')

        return new_obj_info[0]

    #END_CLASS_HEADER

    # config contains contents of config file in a hash or None if it couldn't
    # be found
    def __init__(self, config):
        #BEGIN_CONSTRUCTOR
        self.workspaceURL = config['workspace-url']
        self.shockURL = config['shock-url']
        self.handleURL = config['handle-service-url']
        self.scratch = os.path.abspath(config['scratch'])
        # HACK!! temporary hack for issue where megahit fails on mac because of silent named pipe error
        #self.host_scratch = self.scratch
        self.scratch = os.path.join('/kb','module','local_scratch')
        # end hack
        if not os.path.exists(self.scratch):
            os.makedirs(self.scratch)

        #END_CONSTRUCTOR
        pass

    def BLASTn_Search(self, ctx, params):
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN BLASTn_Search
        console = []
        invalid_msgs = []
        self.log(console,'Running BLASTn_Search with params=')
        self.log(console, "\n"+pformat(params))
        report = ''
#        report = 'Running BLASTn_Search with params='
#        report += "\n"+pformat(params)


        #### do some basic checks
        #
        if 'workspace_name' not in params:
            raise ValueError('workspace_name parameter is required')
#        if 'input_one_name' not in params and 'input_one_sequence' not in params:
#            raise ValueError('input_one_sequence or input_one_name parameter is required')
        if 'input_one_name' not in params:
            raise ValueError('input_one_name parameter is required')
        if 'input_many_name' not in params:
            raise ValueError('input_many_name parameter is required')
        if 'output_filtered_name' not in params:
            raise ValueError('output_filtered_name parameter is required')


        # Write the input_one_sequence to a SingleEndLibrary object
        #
        if 'input_one_sequence' in params \
                and params['input_one_sequence'] != None \
                and params['input_one_sequence'] != "Optionally enter DNA sequence...":
            input_one_file_name = params['input_one_name']
            one_forward_reads_file_path = os.path.join(self.scratch,input_one_file_name)
            one_forward_reads_file_handle = open(one_forward_reads_file_path, 'w', 0)
            self.log(console, 'writing query reads file: '+str(one_forward_reads_file_path))

#            input_sequence_buf = params['input_one_sequence'].split("\n")
#            one_forward_reads_file_handle.write('>'+params['input_one_name']+"\n")
#            query_line_seen = False
#            for line in input_sequence_buf:
#                if not line.startswith('>'):
#                    one_forward_reads_file_handle.write(line+"\n")
#                else:
#                    if query_line_seen:
#                        break
#                    query_line_seen = True
#            one_forward_reads_file_handle.close();

            fastq_format = False
            input_sequence_buf = params['input_one_sequence']
            if input_sequence_buf.startswith('@'):
                fastq_format = True
                #self.log(console,"INPUT_SEQ BEFORE: '''\n"+input_sequence_buf+"\n'''")  # DEBUG
            input_sequence_buf = input_sequence_buf.strip()
            input_sequence_buf = re.sub ('&apos;', "'", input_sequence_buf)
            input_sequence_buf = re.sub ('&quot;', '"', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#39;',  "'", input_sequence_buf)
#        input_sequence_buf = re.sub ('&#34;',  '"', input_sequence_buf)
#        input_sequence_buf = re.sub ('&lt;;',  '<', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#60;',  '<', input_sequence_buf)
#        input_sequence_buf = re.sub ('&gt;',   '>', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#62;',  '>', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#36;',  '$', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#37;',  '%', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#47;',  '/', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#63;',  '?', input_sequence_buf)
##        input_sequence_buf = re.sub ('&#92;',  chr(92), input_sequence_buf)  # FIX LATER
#        input_sequence_buf = re.sub ('&#96;',  '`', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#124;', '|', input_sequence_buf)
#        input_sequence_buf = re.sub ('&amp;', '&', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#38;', '&', input_sequence_buf)
#        self.log(console,"INPUT_SEQ AFTER: '''\n"+input_sequence_buf+"\n'''")  # DEBUG

            DNA_pattern = re.compile("^[acgtuACGTU ]+$")
            space_pattern = re.compile("^[ \t]*$")
            split_input_sequence_buf = input_sequence_buf.split("\n")

            # no header rows, just sequence
            if not input_sequence_buf.startswith('>') and not input_sequence_buf.startswith('@'):
                one_forward_reads_file_handle.write('>'+params['input_one_name']+"\n")
                for line in split_input_sequence_buf:
                    if not space_pattern.match(line):
                        line = re.sub (" ","",line)
                        line = re.sub ("\t","",line)
                        if not DNA_pattern.match(line):
                            self.log(invalid_msgs,"BAD record:\n"+line+"\n")
                            continue
                        one_forward_reads_file_handle.write(line.lower()+"\n")
                one_forward_reads_file_handle.close()

            else:
                # format checks
                for i,line in enumerate(split_input_sequence_buf):
                    if line.startswith('>') or line.startswith('@'):
                        if not DNA_pattern.match(split_input_sequence_buf[i+1]):
                            if fastq_format:
                                bad_record = "\n".join([split_input_sequence_buf[i],
                                                        split_input_sequence_buf[i+1],
                                                        split_input_sequence_buf[i+2],
                                                        split_input_sequence_buf[i+3]])
                            else:
                                bad_record = "\n".join([split_input_sequence_buf[i],
                                                    split_input_sequence_buf[i+1]])
                            self.log(invalid_msgs,"BAD record:\n"+bad_record+"\n")
                        if fastq_format and line.startswith('@'):
                            format_ok = True
                            seq_len = len(split_input_sequence_buf[i+1])
                            if not seq_len > 0:
                                format_ok = False
                            if not split_input_sequence_buf[i+2].startswith('+'):
                                format_ok = False
                            if not seq_len == len(split_input_sequence_buf[i+3]):
                                format_ok = False
                            if not format_ok:
                                bad_record = "\n".join([split_input_sequence_buf[i],
                                                    split_input_sequence_buf[i+1],
                                                    split_input_sequence_buf[i+2],
                                                    split_input_sequence_buf[i+3]])
                                self.log(invalid_msgs,"BAD record:\n"+bad_record+"\n")

                # write that sucker, removing spaces
                #
                #forward_reads_file_handle.write(input_sequence_buf)        input_sequence_buf = re.sub ('&quot;', '"', input_sequence_buf)
                for i,line in enumerate(split_input_sequence_buf):
                    if line.startswith('>'):
                        record_buf = []
                        record_buf.append(line)
                        for j in range(i+1,len(split_input_sequence_buf)):
                            if split_input_sequence_buf[j].startswith('>'):
                                break
                            seq_line = re.sub (" ","",split_input_sequence_buf[j])
                            seq_line = re.sub ("\t","",seq_line)
                            seq_line = seq_line.lower()
                            record_buf.append(seq_line)
                        record = "\n".join(record_buf)+"\n"
                        one_forward_reads_file_handle.write(record)
                        break  # only want first record
                    elif line.startswith('@'):
                        seq_line = re.sub (" ","",split_input_sequence_buf[i+1])
                        seq_line = re.sub ("\t","",seq_line)
                        seq_line = seq_line.lower()
                        qual_line = re.sub (" ","",split_input_sequence_buf[i+3])
                        qual_line = re.sub ("\t","",qual_line)
                        record = "\n".join([line, seq_line, split_input_sequence_buf[i+2], qual_line])+"\n"
                        one_forward_reads_file_handle.write(record)
                        break  # only want first record

                one_forward_reads_file_handle.close()


            # load the method provenance from the context object
            #
            self.log(console,"SETTING PROVENANCE")  # DEBUG
            provenance = [{}]
            if 'provenance' in ctx:
                provenance = ctx['provenance']
            # add additional info to provenance here, in this case the input data object reference
                provenance[0]['input_ws_objects'] = []
                provenance[0]['service'] = 'kb_blast'
                provenance[0]['method'] = 'BLASTn_Search'

                
                # Upload results
                #
                self.log(console,"UPLOADING QUERY OBJECT")  # DEBUG

                sequencing_tech = 'N/A'
                self.upload_SingleEndLibrary_to_shock_and_ws (ctx,
                                                      console,  # DEBUG
                                                      params['workspace_name'],
                                                      params['input_one_name'],
                                                      one_forward_reads_file_path,
                                                      provenance,
                                                      sequencing_tech
                                                      )

            self.log(console, 'done')

        #### Get the input_one object
        ##
        try:
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_one_name']}])
            data = objects[0]['data']
            info = objects[0]['info']
            # Object Info Contents
            # absolute ref = info[6] + '/' + info[0] + '/' + info[4]
            # 0 - obj_id objid
            # 1 - obj_name name
            # 2 - type_string type
            # 3 - timestamp save_date
            # 4 - int version
            # 5 - username saved_by
            # 6 - ws_id wsid
            # 7 - ws_name workspace
            # 8 - string chsum
            # 9 - int size 
            # 10 - usermeta meta
            one_type_name = info[2].split('.')[1].split('-')[0]
        except Exception as e:
            raise ValueError('Unable to fetch input_one_name object from workspace: ' + str(e))
        #to get the full stack trace: traceback.format_exc()

        if 'input_one_sequence' in params \
                and params['input_one_sequence'] != None \
                and params['input_one_sequence'] != "Optionally enter DNA sequence..." \
                and one_type_name != 'SingleEndLibrary':

            self.log(invalid_msgs,"ERROR: Mismatched input type for Query Object: "+params['input_one_name']+" should be SingleEndLibrary instead of: "+one_type_name)


        # Handle overloading (input_one can be Feature, SingleEndLibrary, or FeatureSet)
        #
        if one_type_name == 'SingleEndLibrary':
            try:
                if 'lib' in data:
                    one_forward_reads = data['lib']['file']
                elif 'handle' in data:
                    one_forward_reads = data['handle']
                else:
                    self.log(console,"bad structure for 'one_forward_reads'")
                    raise ValueError("bad structure for 'one_forward_reads'")

                ### NOTE: this section is what could be replaced by the transform services
                one_forward_reads_file_path = os.path.join(self.scratch,one_forward_reads['file_name'])
                one_forward_reads_file_handle = open(one_forward_reads_file_path, 'w', 0)
                self.log(console, 'downloading reads file: '+str(one_forward_reads_file_path))
                headers = {'Authorization': 'OAuth '+ctx['token']}
                r = requests.get(one_forward_reads['url']+'/node/'+one_forward_reads['id']+'?download', stream=True, headers=headers)
                for chunk in r.iter_content(1024):
                    one_forward_reads_file_handle.write(chunk)
                one_forward_reads_file_handle.close();
                self.log(console, 'done')
                ### END NOTE


                # remove carriage returns
                new_file_path = one_forward_reads_file_path+"-CRfree"
                new_file_handle = open(new_file_path, 'w', 0)
                one_forward_reads_file_handle = open(one_forward_reads_file_path, 'r', 0)
                for line in one_forward_reads_file_handle:
                    line = re.sub("\r","",line)
                    new_file_handle.write(line)
                one_forward_reads_file_handle.close();
                new_file_handle.close()
                one_forward_reads_file_path = new_file_path


                # convert FASTQ to FASTA (if necessary)
                new_file_path = one_forward_reads_file_path+".fna"
                new_file_handle = open(new_file_path, 'w', 0)
                one_forward_reads_file_handle = open(one_forward_reads_file_path, 'r', 0)
                header = None
                last_header = None
                last_seq_buf = None
                last_line_was_header = False
                was_fastq = False
                for line in one_forward_reads_file_handle:
                    if line.startswith('>'):
                        break
                    elif line.startswith('@'):
                        was_fastq = True
                        header = line[1:]
                        if last_header != None:
                            new_file_handle.write('>'+last_header)
                            new_file_handle.write(last_seq_buf)
                        last_seq_buf = None
                        last_header = header
                        last_line_was_header = True
                    elif last_line_was_header:
                        last_seq_buf = line
                        last_line_was_header = False
                    else:
                        continue
                if last_header != None:
                    new_file_handle.write('>'+last_header)
                    new_file_handle.write(last_seq_buf)

                new_file_handle.close()
                one_forward_reads_file_handle.close()
                if was_fastq:
                    one_forward_reads_file_path = new_file_path

            except Exception as e:
                print(traceback.format_exc())
                raise ValueError('Unable to download single-end read library files: ' + str(e))

        elif one_type_name == 'FeatureSet':
            # retrieve sequences for features
            input_one_featureSet = data
            
            genome2Features = {}
            features = input_one_featureSet['elements']
            for fId in features.keys():
                genomeRef = features[fId][0]
                if genomeRef not in genome2Features:
                    genome2Features[genomeRef] = []
                genome2Features[genomeRef].append(fId)

            # export features to FASTA file
            one_forward_reads_file_path = os.path.join(self.scratch, params['input_one_name']+".fasta")
            self.log(console, 'writing fasta file: '+one_forward_reads_file_path)
            records = []
            for genomeRef in genome2Features:
                genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                these_genomeFeatureIds = genome2Features[genomeRef]
                for feature in genome['features']:
                    if feature['id'] in these_genomeFeatureIds:

                        # BLASTn is nuc-nuc
                        record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genomeRef+"."+feature['id'])
                        records.append(record)
                        SeqIO.write(records, one_forward_reads_file_path, "fasta")
                        break  # just want one record

        elif one_type_name == 'Feature':
            # export feature to FASTA file
            feature = data
            one_forward_reads_file_path = os.path.join(self.scratch, params['input_one_name']+".fasta")
            self.log(console, 'writing fasta file: '+one_forward_reads_file_path)
            # BLASTn is nuc-nuc
            record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description='['+feature['genome_id']+']'+' '+feature['function'])
            #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description='['+feature['genome_id']+']'+' '+feature['function'])
            SeqIO.write([record], one_forward_reads_file_path, "fasta")

        else:
            raise ValueError('Cannot yet handle input_one type of: '+type_name)


        #### Get the input_many object
        ##
        many_forward_reads_file_compression = None
        sequencing_tech = 'N/A'
        try:
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_many_name']}])
            data = objects[0]['data']
            info = objects[0]['info']
            input_many_ref = str(info[6])+'/'+str(info[0])+'/'+str(info[4])
            many_type_name = info[2].split('.')[1].split('-')[0]

            if many_type_name == 'SingleEndLibrary':
                many_type_namespace = info[2].split('.')[0]
                if many_type_namespace == 'KBaseAssembly':
                    file_name = data['handle']['file_name']
                elif many_type_namespace == 'KBaseFile':
                    file_name = data['lib']['file']['file_name']
                else:
                    raise ValueError('bad data type namespace: '+many_type_namespace)
                #self.log(console, 'INPUT_MANY_FILENAME: '+file_name)  # DEBUG
                if file_name[-3:] == ".gz":
                    many_forward_reads_file_compression = 'gz'
                if 'sequencing_tech' in data:
                    sequencing_tech = data['sequencing_tech']

        except Exception as e:
            raise ValueError('Unable to fetch input_many_name object from workspace: ' + str(e))
            #to get the full stack trace: traceback.format_exc()

        # Handle overloading (input_many can be SingleEndLibrary, FeatureSet, Genome, or GenomeSet)
        #
        if many_type_name == 'SingleEndLibrary':

            # DEBUG
            #for k in data:
            #    self.log(console,"SingleEndLibrary ["+k+"]: "+str(data[k]))

            try:
                if 'lib' in data:
                    many_forward_reads = data['lib']['file']
                elif 'handle' in data:
                    many_forward_reads = data['handle']
                else:
                    self.log(console,"bad structure for 'many_forward_reads'")
                    raise ValueError("bad structure for 'many_forward_reads'")
                #if 'lib2' in data:
                #    reverse_reads = data['lib2']['file']
                #elif 'handle_2' in data:
                #    reverse_reads = data['handle_2']
                #else:
                #    reverse_reads={}

                ### NOTE: this section is what could be replaced by the transform services
                many_forward_reads_file_path = os.path.join(self.scratch,many_forward_reads['file_name'])
                many_forward_reads_file_handle = open(many_forward_reads_file_path, 'w', 0)
                self.log(console, 'downloading reads file: '+str(many_forward_reads_file_path))
                headers = {'Authorization': 'OAuth '+ctx['token']}
                r = requests.get(many_forward_reads['url']+'/node/'+many_forward_reads['id']+'?download', stream=True, headers=headers)
                for chunk in r.iter_content(1024):
                    many_forward_reads_file_handle.write(chunk)
                many_forward_reads_file_handle.close();
                self.log(console, 'done')
                ### END NOTE


                # remove carriage returns
                new_file_path = many_forward_reads_file_path+"-CRfree"
                new_file_handle = open(new_file_path, 'w', 0)
                many_forward_reads_file_handle = open(many_forward_reads_file_path, 'r', 0)
                for line in many_forward_reads_file_handle:
                    line = re.sub("\r","",line)
                    new_file_handle.write(line)
                many_forward_reads_file_handle.close();
                new_file_handle.close()
                many_forward_reads_file_path = new_file_path


                # convert FASTQ to FASTA (if necessary)
                new_file_path = many_forward_reads_file_path+".fna"
                new_file_handle = open(new_file_path, 'w', 0)
                if many_forward_reads_file_compression == 'gz':
                    many_forward_reads_file_handle = gzip.open(many_forward_reads_file_path, 'r', 0)
                else:
                    many_forward_reads_file_handle = open(many_forward_reads_file_path, 'r', 0)
                header = None
                last_header = None
                last_seq_buf = None
                last_line_was_header = False
                was_fastq = False
                for line in many_forward_reads_file_handle:
                    if line.startswith('>'):
                        break
                    elif line.startswith('@'):
                        was_fastq = True
                        header = line[1:]
                        if last_header != None:
                            new_file_handle.write('>'+last_header)
                            new_file_handle.write(last_seq_buf)
                        last_seq_buf = None
                        last_header = header
                        last_line_was_header = True
                    elif last_line_was_header:
                        last_seq_buf = line
                        last_line_was_header = False
                    else:
                        continue
                if last_header != None:
                    new_file_handle.write('>'+last_header)
                    new_file_handle.write(last_seq_buf)

                new_file_handle.close()
                many_forward_reads_file_handle.close()
                if was_fastq:
                    many_forward_reads_file_path = new_file_path

            except Exception as e:
                print(traceback.format_exc())
                raise ValueError('Unable to download single-end read library files: ' + str(e))

        # FeatureSet
        #
        elif many_type_name == 'FeatureSet':
            # retrieve sequences for features
            input_many_featureSet = data

            genome2Features = {}
            features = input_many_featureSet['elements']
            for fId in features.keys():
                genomeRef = features[fId][0]
                if genomeRef not in genome2Features:
                    genome2Features[genomeRef] = []
                genome2Features[genomeRef].append(fId)

            # export features to FASTA file
            many_forward_reads_file_path = os.path.join(self.scratch, params['input_many_name']+".fasta")
            self.log(console, 'writing fasta file: '+many_forward_reads_file_path)
            records = []
            feature_written = dict()
            for genomeRef in genome2Features:
                genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                these_genomeFeatureIds = genome2Features[genomeRef]
                for feature in genome['features']:
                    if feature['id'] in these_genomeFeatureIds:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
                            # BLASTn is nuc-nuc
                            record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                            #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                            records.append(record)
            SeqIO.write(records, many_forward_reads_file_path, "fasta")


        # Genome
        #
        elif many_type_name == 'Genome':
            input_many_genome = data
            many_forward_reads_file_dir = self.scratch
            many_forward_reads_file = params['input_many_name']+".fasta"

            many_forward_reads_file_path = self.KB_SDK_data2file_Genome2Fasta (
                genome_object = input_many_genome,
                file          = many_forward_reads_file,
                dir           = many_forward_reads_file_dir,
                console       = console,
                invalid_msgs  = invalid_msgs,
                residue_type  = 'nucleotide',
                feature_type  = 'ALL',
                record_id_pattern = '%%feature_id%%',
                record_desc_pattern = '[%%genome_id%%]',
                case='upper',
                linewrap=50)


        # GenomeSet
        #
        elif many_type_name == 'GenomeSet':
            input_many_genomeSet = data

            # export features to FASTA file
            many_forward_reads_file_path = os.path.join(self.scratch, params['input_many_name']+".fasta")
            self.log(console, 'writing fasta file: '+many_forward_reads_file_path)

            records = []
            feature_written = dict()
            for genome_name in input_many_genomeSet['elements'].keys():
                if 'ref' in input_many_genomeSet['elements'][genome_name] and \
                         input_many_genomeSet['elements'][genome_name]['ref'] != None:
                    genome = ws.get_objects([{'ref': input_many_genomeSet['elements'][genome_name]['ref']}])[0]['data']
                    for feature in genome['features']:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
                            # BLASTn is nuc-nuc
                            record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                            #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                            records.append(record)

                elif 'data' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['data'] != None:
                    genome = input_many_genomeSet['elements'][genome_name]['data']
                    for feature in genome['features']:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
                            # BLASTn is nuc-nuc
                            record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                            #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                            records.append(record)

                else:
                    raise ValueError('genome '+genome_name+' missing')

            SeqIO.write(records, many_forward_reads_file_path, "fasta")
            
        # Missing proper input_many_type
        #
        else:
            raise ValueError('Cannot yet handle input_many type of: '+type_name)


        # FORMAT DB
        #
        # OLD SYNTAX: formatdb -i $database -o T -p F -> $database.nsq or $database.00.nsq
        # NEW SYNTAX: makeblastdb -in $database -parse_seqids -dbtype prot/nucl -out <basename>
        makeblastdb_cmd = [self.Make_BLAST_DB]

        # check for necessary files
        if not os.path.isfile(self.Make_BLAST_DB):
            raise ValueError("no such file '"+self.Make_BLAST_DB+"'")
        if not os.path.isfile(many_forward_reads_file_path):
            raise ValueError("no such file '"+many_forward_reads_file_path+"'")
        elif not os.path.getsize(many_forward_reads_file_path) > 0:
            raise ValueError("empty file '"+many_forward_reads_file_path+"'")

        makeblastdb_cmd.append('-in')
        makeblastdb_cmd.append(many_forward_reads_file_path)
        makeblastdb_cmd.append('-parse_seqids')
        makeblastdb_cmd.append('-dbtype')
        makeblastdb_cmd.append('nucl')
        makeblastdb_cmd.append('-out')
        makeblastdb_cmd.append(many_forward_reads_file_path)

        # Run Make_BLAST_DB, capture output as it happens
        #
        self.log(console, 'RUNNING Make_BLAST_DB:')
        self.log(console, '    '+' '.join(makeblastdb_cmd))
#        report += "\n"+'running Make_BLAST_DB:'+"\n"
#        report += '    '+' '.join(makeblastdb_cmd)+"\n"

        p = subprocess.Popen(makeblastdb_cmd, \
                             cwd = self.scratch, \
                             stdout = subprocess.PIPE, \
                             stderr = subprocess.STDOUT, \
                             shell = False)

        while True:
            line = p.stdout.readline()
            if not line: break
            self.log(console, line.replace('\n', ''))

        p.stdout.close()
        p.wait()
        self.log(console, 'return code: ' + str(p.returncode))
        if p.returncode != 0:
            raise ValueError('Error running makeblastdb, return code: '+str(p.returncode) + 
                '\n\n'+ '\n'.join(console))

        # Check for db output
        if not os.path.isfile(many_forward_reads_file_path+".nsq") and not os.path.isfile(many_forward_reads_file_path+".00.nsq"):
            raise ValueError("makeblastdb failed to create DB file '"+many_forward_reads_file_path+".nsq'")
        elif not os.path.getsize(many_forward_reads_file_path+".nsq") > 0 and not os.path.getsize(many_forward_reads_file_path+".00.nsq") > 0:
            raise ValueError("makeblastdb created empty DB file '"+many_forward_reads_file_path+".nsq'")


        ### Construct the BLAST command
        #
        # OLD SYNTAX: $blast -q $q -G $G -E $E -m $m -e $e_value -v $limit -b $limit -K $limit -p blastn -i $fasta_file -d $database -o $out_file
        # NEW SYNTAX: blastn -query <queryfile> -db <basename> -out <out_aln_file> -outfmt 0/7 (8 became 7) -evalue <e_value> -dust no (DNA) -seg no (AA) -num_threads <num_cores>
        #
        blast_bin = self.BLASTn
        blast_cmd = [blast_bin]

        # check for necessary files
        if not os.path.isfile(blast_bin):
            raise ValueError("no such file '"+blast_bin+"'")
        if not os.path.isfile(one_forward_reads_file_path):
            raise ValueError("no such file '"+one_forward_reads_file_path+"'")
        elif not os.path.getsize(one_forward_reads_file_path) > 0:
            raise ValueError("empty file '"+one_forward_reads_file_path+"'")
        if not os.path.isfile(many_forward_reads_file_path):
            raise ValueError("no such file '"+many_forward_reads_file_path+"'")
        elif not os.path.getsize(many_forward_reads_file_path):
            raise ValueError("empty file '"+many_forward_reads_file_path+"'")

        # set the output path
        timestamp = int((datetime.utcnow() - datetime.utcfromtimestamp(0)).total_seconds()*1000)
        output_dir = os.path.join(self.scratch,'output.'+str(timestamp))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_aln_file_path = os.path.join(output_dir, 'alnout.txt');
        output_filtered_fasta_file_path = os.path.join(output_dir, 'output_filtered.fna');

        # this is command for basic search mode
        blast_cmd.append('-query')
        blast_cmd.append(one_forward_reads_file_path)
        blast_cmd.append('-db')
        blast_cmd.append(many_forward_reads_file_path)
        blast_cmd.append('-out')
        blast_cmd.append(output_aln_file_path)
        blast_cmd.append('-outfmt')
        blast_cmd.append('7')
        blast_cmd.append('-evalue')
        blast_cmd.append(str(params['e_value']))

        # options
        if 'maxaccepts' in params:
            if params['maxaccepts']:
                blast_cmd.append('-max_target_seqs')
                blast_cmd.append(str(params['maxaccepts']))

        # Run BLAST, capture output as it happens
        #
        self.log(console, 'RUNNING BLAST:')
        self.log(console, '    '+' '.join(blast_cmd))
#        report += "\n"+'running BLAST:'+"\n"
#        report += '    '+' '.join(blast_cmd)+"\n"

        p = subprocess.Popen(blast_cmd, \
                             cwd = self.scratch, \
                             stdout = subprocess.PIPE, \
                             stderr = subprocess.STDOUT, \
                             shell = False)

        while True:
            line = p.stdout.readline()
            if not line: break
            self.log(console, line.replace('\n', ''))

        p.stdout.close()
        p.wait()
        self.log(console, 'return code: ' + str(p.returncode))
        if p.returncode != 0:
            raise ValueError('Error running BLAST, return code: '+str(p.returncode) + 
                '\n\n'+ '\n'.join(console))


        # get query_len for filtering later
        #
        query_len = 0
        with open(one_forward_reads_file_path, 'r', 0) as query_file_handle:
            for line in query_file_handle:
                if line.startswith('>'):
                    continue
                query_len += len(re.sub(r" ","", line.rstrip())) 
        

        # Parse the BLAST tabular output and store ids to filter many set to make filtered object to save back to KBase
        #
        self.log(console, 'PARSING BLAST ALIGNMENT OUTPUT')
        if not os.path.isfile(output_aln_file_path):
            raise ValueError("failed to create BLAST output: "+output_aln_file_path)
        elif not os.path.getsize(output_aln_file_path) > 0:
            raise ValueError("created empty file for BLAST output: "+output_aln_file_path)
        hit_seq_ids = dict()
        output_aln_file_handle = open (output_aln_file_path, "r", 0)
        output_aln_buf = output_aln_file_handle.readlines()
        output_aln_file_handle.close()
        hit_total = 0
        high_bitscore_line = dict()
        high_bitscore_score = dict()
        high_bitscore_ident = dict()
        high_bitscore_alnlen = dict()
        hit_order = []
        hit_buf = []
        header_done = False
        for line in output_aln_buf:
            if line.startswith('#'):
                if not header_done:
                    hit_buf.append(line)
                continue
            header_done = True
            #self.log(console,'HIT LINE: '+line)  # DEBUG
            hit_info = line.split("\t")
            hit_seq_id     = hit_info[1]
            hit_ident      = float(hit_info[2]) / 100.0
            hit_aln_len    = hit_info[3]
            hit_mismatches = hit_info[4]
            hit_gaps       = hit_info[5]
            hit_q_beg      = hit_info[6]
            hit_q_end      = hit_info[7]
            hit_t_beg      = hit_info[8]
            hit_t_end      = hit_info[9]
            hit_e_value    = hit_info[10]
            hit_bitscore   = hit_info[11]

            # BLAST SOMETIMES ADDS THIS TO IDs.  NO IDEA WHY, BUT GET RID OF IT!
            if hit_seq_id.startswith('gnl|'):
                hit_seq_id = hit_seq_id[4:]

            try:
                if float(hit_bitscore) > float(high_bitscore_score[hit_seq_id]):
                    high_bitscore_score[hit_seq_id] = hit_bitscore
                    high_bitscore_ident[hit_seq_id] = hit_ident
                    high_bitscore_alnlen[hit_seq_id] = hit_aln_len
                    high_bitscore_line[hit_seq_id] = line
            except:
                hit_order.append(hit_seq_id)
                high_bitscore_score[hit_seq_id] = hit_bitscore
                high_bitscore_ident[hit_seq_id] = hit_ident
                high_bitscore_alnlen[hit_seq_id] = hit_aln_len
                high_bitscore_line[hit_seq_id] = line

        for hit_seq_id in hit_order:
            hit_buf.append(high_bitscore_line[hit_seq_id])

            if 'ident_thresh' in params and float(params['ident_thresh']) > float(high_bitscore_ident[hit_seq_id]):
                continue
            if 'bitscore' in params and float(params['bitscore']) > float(high_bitscore_score[hit_seq_id]):
                continue
            if 'overlap_fraction' in params and float(params['overlap_fraction']) > float(high_bitscore_alnlen[hit_seq_id])/float(query_len):
                continue
            
            hit_total += 1
            hit_seq_ids[hit_seq_id] = True
            self.log(console, "HIT: '"+hit_seq_id+"'")  # DEBUG
        

        self.log(console, 'EXTRACTING HITS FROM INPUT')
        self.log(console, 'MANY_TYPE_NAME: '+many_type_name)  # DEBUG


        # SingleEndLibrary input -> SingleEndLibrary output
        #
        if many_type_name == 'SingleEndLibrary':

            #  Note: don't use SeqIO.parse because loads everything into memory
            #
#            with open(many_forward_reads_file_path, 'r', -1) as many_forward_reads_file_handle, open(output_filtered_fasta_file_path, 'w', -1) as output_filtered_fasta_file_handle:
            output_filtered_fasta_file_handle = open(output_filtered_fasta_file_path, 'w', -1)
            if many_forward_reads_file_compression == 'gz':
                many_forward_reads_file_handle = gzip.open(many_forward_reads_file_path, 'r', -1)
            else:
                many_forward_reads_file_handle = open(many_forward_reads_file_path, 'r', -1)

            seq_total = 0;
            filtered_seq_total = 0
            last_seq_buf = []
            last_seq_id = None
            last_header = None
            pattern = re.compile('^\S*')
            for line in many_forward_reads_file_handle:
                if line.startswith('>'):
                    #self.log(console, 'LINE: '+line)  # DEBUG
                    seq_total += 1
                    seq_id = line[1:]  # removes '>'
                    seq_id = pattern.findall(seq_id)[0]

                    if last_seq_id != None:
                        #self.log(console, 'ID: '+last_seq_id)  # DEBUG
                        try:
                            in_filtered_set = hit_seq_ids[last_seq_id]
                            #self.log(console, 'FOUND HIT '+last_seq_id)  # DEBUG
                            filtered_seq_total += 1
                            output_filtered_fasta_file_handle.write(last_header)
                            output_filtered_fasta_file_handle.writelines(last_seq_buf)
                        except:
                            pass
                        
                    last_seq_buf = []
                    last_seq_id = seq_id
                    last_header = line
                else:
                    last_seq_buf.append(line)

            if last_seq_id != None:
                #self.log(console, 'ID: '+last_seq_id)  # DEBUG
                try:
                    in_filtered_set = hit_seq_ids[last_seq_id]
                    #self.log(console, 'FOUND HIT: '+last_seq_id)  # DEBUG
                    filtered_seq_total += 1
                    output_filtered_fasta_file_handle.write(last_header)
                    output_filtered_fasta_file_handle.writelines(last_seq_buf)
                except:
                    pass
                
            last_seq_buf = []
            last_seq_id = None
            last_header = None

            many_forward_reads_file_handle.close()
            output_filtered_fasta_file_handle.close()

            if filtered_seq_total != hit_total:
                self.log(console,'hits in BLAST alignment output '+str(hit_total)+' != '+str(filtered_seq_total)+' matched sequences in input file')
                raise ValueError('hits in BLAST alignment output '+str(hit_total)+' != '+str(filtered_seq_total)+' matched sequences in input file')


        # FeatureSet input -> FeatureSet output
        #
        elif many_type_name == 'FeatureSet':

            seq_total = len(input_many_featureSet['elements'].keys())

            output_featureSet = dict()
            if 'description' in input_many_featureSet and input_many_featureSet['description'] != None:
                output_featureSet['description'] = input_many_featureSet['description'] + " - BLASTn_Search filtered"
            else:
                output_featureSet['description'] = "BLASTn_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()
            if 'element_ordering' in input_many_featureSet and input_many_featureSet['element_ordering'] != None:
                for fId in input_many_featureSet['element_ordering']:
                    try:
                        in_filtered_set = hit_seq_ids[fId]
                        #self.log(console, 'FOUND HIT '+fId)  # DEBUG
                        output_featureSet['element_ordering'].append(fId)
                        output_featureSet['elements'][fId] = input_many_featureSet['elements'][fId]
                    except:
                        pass
            else:
                fId_list = input_many_featureSet['elements'].keys()
                self.log(console,"ADDING FEATURES TO FEATURESET")
                for fId in sorted(fId_list):
                    try:
                        #self.log(console,"checking '"+fId+"'")
                        in_filtered_set = hit_seq_ids[fId]
                        #self.log(console, 'FOUND HIT '+fId)  # DEBUG
                        output_featureSet['element_ordering'].append(fId)
                        output_featureSet['elements'][fId] = input_many_featureSet['elements'][fId]
                    except:
                        pass


        # Parse Genome hits into FeatureSet
        #
        elif many_type_name == 'Genome':
            seq_total = 0

            output_featureSet = dict()
            if 'scientific_name' in input_many_genome and input_many_genome['scientific_name'] != None:
                output_featureSet['description'] = input_many_genome['scientific_name'] + " - BLASTn_Search filtered"
            else:
                output_featureSet['description'] = "BLASTn_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()
            for feature in input_many_genome['features']:
                seq_total += 1
                try:
                    in_filtered_set = hit_seq_ids[feature['id']]
                    #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
                    output_featureSet['element_ordering'].append(feature['id'])
                    output_featureSet['elements'][feature['id']] = [input_many_ref]
                except:
                    pass

        # Parse GenomeSet hits into FeatureSet
        #
        elif many_type_name == 'GenomeSet':
            seq_total = 0

            output_featureSet = dict()
            if 'description' in input_many_genomeSet and input_many_genomeSet['description'] != None:
                output_featureSet['description'] = input_many_genomeSet['description'] + " - BLASTn_Search filtered"
            else:
                output_featureSet['description'] = "BLASTn_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()

            for genome_name in input_many_genomeSet['elements'].keys():
                if 'ref' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['ref'] != None:
                    genomeRef = input_many_genomeSet['elements'][genome_name]['ref']
                    genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                    for feature in genome['features']:
                        seq_total += 1
                        try:
                            in_filtered_set = hit_seq_ids[feature['id']]
                            #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
                            output_featureSet['element_ordering'].append(feature['id'])
                            output_featureSet['elements'][feature['id']] = [genomeRef]
                        except:
                            pass

                elif 'data' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['data'] != None:
#                    genome = input_many_genomeSet['elements'][genome_name]['data']
#                    for feature in genome['features']:
#                        #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
#                        seq_total += 1
#                        try:
#                            in_filtered_set = hit_seq_ids[feature['id']]
#                            #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
#                            output_featureSet['element_ordering'].append(feature['id'])
                    raise ValueError ("FAILURE: unable to address genome object that is stored within 'data' field of genomeSet object")
#                            output_featureSet['elements'][feature['id']] = [genomeRef_is_inside_data_within_genomeSet_object_and_that_cant_be_addressed]
#                        except:
#                            pass


        # load the method provenance from the context object
        #
        self.log(console,"SETTING PROVENANCE")  # DEBUG
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects'] = []
        if 'input_one_name' in params and params['input_one_name'] != None:
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_one_name'])
        provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_many_name'])
        provenance[0]['service'] = 'kb_blast'
        provenance[0]['method'] = 'BLASTn_Search'


        # Upload results
        #
        if len(invalid_msgs) == 0:
            self.log(console,"UPLOADING RESULTS")  # DEBUG

            if many_type_name == 'SingleEndLibrary':
            
                # input SingleEndLibrary -> upload SingleEndLibrary
                #
                self.upload_SingleEndLibrary_to_shock_and_ws (ctx,
                                                          console,  # DEBUG
                                                          params['workspace_name'],
                                                          params['output_filtered_name'],
                                                          output_filtered_fasta_file_path,
                                                          provenance,
                                                          sequencing_tech
                                                         )

            else:  # input FeatureSet, Genome, and GenomeSet -> upload FeatureSet output
                new_obj_info = ws.save_objects({
                            'workspace': params['workspace_name'],
                            'objects':[{
                                    'type': 'KBaseCollections.FeatureSet',
                                    'data': output_featureSet,
                                    'name': params['output_filtered_name'],
                                    'meta': {},
                                    'provenance': provenance
                                }]
                        })

        # build output report object
        #
        self.log(console,"BUILDING REPORT")  # DEBUG
        if len(invalid_msgs) == 0:
            report += 'sequences in many set: '+str(seq_total)+"\n"
            report += 'sequences in hit set:  '+str(hit_total)+"\n"
            report += "\n"
            for line in hit_buf:
                report += line
            reportObj = {
                'objects_created':[{'ref':params['workspace_name']+'/'+params['output_filtered_name'], 'description':'BLASTn_Search hits'}],
                'text_message':report
                }
        else:
            report += "FAILURE\n\n"+"\n".join(invalid_msgs)+"\n"
            reportObj = {
                'objects_created':[],
                'text_message':report
                }

        reportName = 'blast_report_'+str(hex(uuid.getnode()))
        report_obj_info = ws.save_objects({
#                'id':info[6],
                'workspace':params['workspace_name'],
                'objects':[
                    {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance
                    }
                ]
            })[0]

        self.log(console,"BUILDING RETURN OBJECT")
#        returnVal = { 'output_report_name': reportName,
#                      'output_report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
#                      'output_filtered_ref': params['workspace_name']+'/'+params['output_filtered_name']
#                      }
        returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
        self.log(console,"BLASTn_Search DONE")
        #END BLASTn_Search

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method BLASTn_Search return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]


    def BLASTp_Search(self, ctx, params):
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN BLASTp_Search
        console = []
        invalid_msgs = []
        self.log(console,'Running BLASTp_Search with params=')
        self.log(console, "\n"+pformat(params))
        report = ''
#        report = 'Running BLASTp_Search with params='
#        report += "\n"+pformat(params)
        protein_sequence_found_in_one_input = False
        protein_sequence_found_in_many_input = False


        #### do some basic checks
        #
        if 'workspace_name' not in params:
            raise ValueError('workspace_name parameter is required')
#        if 'input_one_name' not in params and 'input_one_sequence' not in params:
#            raise ValueError('input_one_sequence or input_one_name parameter is required')
        if 'input_one_name' not in params:
            raise ValueError('input_one_name parameter is required')
        if 'input_many_name' not in params:
            raise ValueError('input_many_name parameter is required')
        if 'output_filtered_name' not in params:
            raise ValueError('output_filtered_name parameter is required')


        # Write the input_one_sequence to file
        #
        if 'input_one_sequence' in params \
                and params['input_one_sequence'] != None \
                and params['input_one_sequence'] != "Optionally enter PROTEIN sequence...":
            #input_one_file_name = params['input_one_name']
            input_one_name = 'query.faa'
            input_one_file_name = input_one_name
            one_forward_reads_file_path = os.path.join(self.scratch,input_one_file_name)
            one_forward_reads_file_handle = open(one_forward_reads_file_path, 'w', 0)
            self.log(console, 'writing query reads file: '+str(one_forward_reads_file_path))

#            input_sequence_buf = params['input_one_sequence'].split("\n")
#            one_forward_reads_file_handle.write('>'+params['input_one_name']+"\n")
#            query_line_seen = False
#            for line in input_sequence_buf:
#                if not line.startswith('>'):
#                    one_forward_reads_file_handle.write(line+"\n")
#                else:
#                    if query_line_seen:
#                        break
#                    query_line_seen = True
#            one_forward_reads_file_handle.close();

            input_sequence_buf = params['input_one_sequence']
            input_sequence_buf = input_sequence_buf.strip()
            space_pattern = re.compile("^[ \t]*$")
            split_input_sequence_buf = input_sequence_buf.split("\n")

            # no header rows, just sequence
            if not input_sequence_buf.startswith('>'):
                one_forward_reads_file_handle.write('>'+input_one_name+"\n")
                for line in split_input_sequence_buf:
                    if not space_pattern.match(line):
                        line = re.sub (" ","",line)
                        line = re.sub ("\t","",line)
                        one_forward_reads_file_handle.write(line.upper()+"\n")
                one_forward_reads_file_handle.close()

            else:
                # write that sucker, removing spaces
                #
                #forward_reads_file_handle.write(input_sequence_buf)        input_sequence_buf = re.sub ('&quot;', '"', input_sequence_buf)
                for i,line in enumerate(split_input_sequence_buf):
                    if line.startswith('>'):
                        record_buf = []
                        record_buf.append(line)
                        for j in range(i+1,len(split_input_sequence_buf)):
                            if split_input_sequence_buf[j].startswith('>'):
                                break
                            seq_line = re.sub (" ","",split_input_sequence_buf[j])
                            seq_line = re.sub ("\t","",seq_line)
                            seq_line = seq_line.upper()
                            record_buf.append(seq_line)
                        record = "\n".join(record_buf)+"\n"
                        one_forward_reads_file_handle.write(record)
                        break  # only want first record
                one_forward_reads_file_handle.close()


        #### Get the input_one object
        ##
        elif 'input_one_name' in params and params['input_one_name'] != None:
            try:
                ws = workspaceService(self.workspaceURL, token=ctx['token'])
                objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_one_name']}])
                data = objects[0]['data']
                info = objects[0]['info']
                # Object Info Contents
                # absolute ref = info[6] + '/' + info[0] + '/' + info[4]
                # 0 - obj_id objid
                # 1 - obj_name name
                # 2 - type_string type
                # 3 - timestamp save_date
                # 4 - int version
                # 5 - username saved_by
                # 6 - ws_id wsid
                # 7 - ws_name workspace
                # 8 - string chsum
                # 9 - int size 
                # 10 - usermeta meta
                one_type_name = info[2].split('.')[1].split('-')[0]
            except Exception as e:
                raise ValueError('Unable to fetch input_one_name object from workspace: ' + str(e))
                #to get the full stack trace: traceback.format_exc()


            # Handle overloading (input_one can be Feature, or FeatureSet)
            #
            if one_type_name == 'FeatureSet':
                # retrieve sequences for features
                input_one_featureSet = data
            
                genome2Features = {}
                features = input_one_featureSet['elements']

                if len(features.keys()) == 0:
                    self.log(console,"No features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                    self.log(invalid_msgs,"No features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                if len(features.keys()) > 1:
                    self.log(console,"Too many features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                    self.log(invalid_msgs,"Too many features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))

                for fId in features.keys():
                    genomeRef = features[fId][0]
                    if genomeRef not in genome2Features:
                        genome2Features[genomeRef] = []
                    genome2Features[genomeRef].append(fId)

                # export features to FASTA file
                one_forward_reads_file_path = os.path.join(self.scratch, params['input_one_name']+".fasta")
                self.log(console, 'writing fasta file: '+one_forward_reads_file_path)
                records = []
                for genomeRef in genome2Features:
                    genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                    these_genomeFeatureIds = genome2Features[genomeRef]
                    for feature in genome['features']:
                        if feature['id'] in these_genomeFeatureIds:
                            # BLASTp is prot-prot
                            #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genomeRef+"."+feature['id'])
                            if feature['type'] != 'CDS':
                                self.log(console,params['input_one_name']+" feature type must be CDS")
                                self.log(invalid_msgs,params['input_one_name']+" feature type must be CDS")
                            elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                                self.log(console,"bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                                raise ValueError ("bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                            else:
                                protein_sequence_found_in_one_input = True
                                record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genomeRef+"."+feature['id'])
                                records.append(record)
                                SeqIO.write(records, one_forward_reads_file_path, "fasta")
                                break  # only want first record

            elif one_type_name == 'Feature':
                # export feature to FASTA file
                feature = data
                one_forward_reads_file_path = os.path.join(self.scratch, params['input_one_name']+".fasta")
                self.log(console, 'writing fasta file: '+one_forward_reads_file_path)
                # BLASTp is prot-prot
                #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description='['+feature['genome_id']+']'+' '+feature['function'])
                if feature['type'] != 'CDS':
                    self.log(console,params['input_one_name']+" feature type must be CDS")
                    self.log(invalid_msgs,params['input_one_name']+" feature type must be CDS")
                elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                    self.log(console,"bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                    raise ValueError("bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                else:
                    protein_sequence_found_in_one_input = True
                    record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description='['+feature['genome_id']+']'+' '+feature['function'])
                    SeqIO.write([record], one_forward_reads_file_path, "fasta")

            else:
                raise ValueError('Cannot yet handle input_one type of: '+type_name)            
        else:
            raise ValueError('Must define either input_one_sequence or input_one_name')


        #### Get the input_many object
        ##
        try:
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_many_name']}])
            data = objects[0]['data']
            info = objects[0]['info']
            input_many_ref = str(info[6])+'/'+str(info[0])+'/'+str(info[4])
            many_type_name = info[2].split('.')[1].split('-')[0]

        except Exception as e:
            raise ValueError('Unable to fetch input_many_name object from workspace: ' + str(e))
            #to get the full stack trace: traceback.format_exc()

        # Handle overloading (input_many can be FeatureSet, Genome, or GenomeSet)
        #
        if many_type_name == 'FeatureSet':
            # retrieve sequences for features
            input_many_featureSet = data

            genome2Features = {}
            features = input_many_featureSet['elements']
            for fId in features.keys():
                genomeRef = features[fId][0]
                if genomeRef not in genome2Features:
                    genome2Features[genomeRef] = []
                genome2Features[genomeRef].append(fId)

            # export features to FASTA file
            many_forward_reads_file_path = os.path.join(self.scratch, params['input_many_name']+".fasta")
            self.log(console, 'writing fasta file: '+many_forward_reads_file_path)
            records = []
            feature_written = dict()
            for genomeRef in genome2Features:
                genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                these_genomeFeatureIds = genome2Features[genomeRef]
                for feature in genome['features']:
                    if feature['id'] in these_genomeFeatureIds:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG

                            # BLASTp is prot-prot
                            if feature['type'] != 'CDS':
                                self.log(console,"skipping non-CDS feature "+feature['id'])
                                continue
                            elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                                self.log(console,"bad CDS feature "+feature['id'])
                                raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                protein_sequence_found_in_many_input = True
                                #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                                record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)
            SeqIO.write(records, many_forward_reads_file_path, "fasta")


        # Genome
        #
        elif many_type_name == 'Genome':
            input_many_genome = data
            many_forward_reads_file_dir = self.scratch
            many_forward_reads_file = params['input_many_name']+".fasta"

            many_forward_reads_file_path = self.KB_SDK_data2file_Genome2Fasta (
                genome_object = input_many_genome,
                file          = many_forward_reads_file,
                dir           = many_forward_reads_file_dir,
                console       = console,
                invalid_msgs  = invalid_msgs,
                residue_type  = 'protein',
                feature_type  = 'CDS',
                record_id_pattern = '%%feature_id%%',
                record_desc_pattern = '[%%genome_id%%]',
                case='upper',
                linewrap=50)

            protein_sequence_found_in_many_input = True  # FIX LATER
            

        # GenomeSet
        #
        elif many_type_name == 'GenomeSet':
            input_many_genomeSet = data

            # export features to FASTA file
            many_forward_reads_file_path = os.path.join(self.scratch, params['input_many_name']+".fasta")
            self.log(console, 'writing fasta file: '+many_forward_reads_file_path)

            records = []
            feature_written = dict()
            for genome_name in input_many_genomeSet['elements'].keys():
                if 'ref' in input_many_genomeSet['elements'][genome_name] and \
                         input_many_genomeSet['elements'][genome_name]['ref'] != None:
                    genome = ws.get_objects([{'ref': input_many_genomeSet['elements'][genome_name]['ref']}])[0]['data']
                    for feature in genome['features']:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
                            # BLASTp is prot-prot
                            #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                            if feature['type'] != 'CDS':
                                #self.log(console,"skipping non-CDS feature "+feature['id'])  # too much chatter for a Genome
                                continue
                            elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                                self.log(console,"bad CDS feature "+feature['id'])
                                if 'dna_sequence' not in feature or feature['dna_sequence'] == None:
                                    raise ValueError("bad CDS feature "+feature['id'])
                                else:
                                    protein_sequence_found_in_many_input = True
                                    protein_translation = self.translate_nuc_to_prot_seq (feature['dna_sequence'], table='11')
                                    self.log(console, "nucleotide_seq: '%s'"%protein_translation)
                                    self.log(console, "protein_seq: '%s'"%protein_translation)
                                    record = SeqRecord(Seq(protein_translation), id=feature['id'], description=genome['id'])
                                    records.append(record)
                                    
                            else:
                                protein_sequence_found_in_many_input = True
                                record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)

                elif 'data' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['data'] != None:
                    genome = input_many_genomeSet['elements'][genome_name]['data']
                    for feature in genome['features']:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
                            # BLASTp is prot-prot
                            #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                            if feature['type'] != 'CDS':
                                continue
                            elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                                self.log(console,"bad CDS feature "+feature['id'])
                                raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                protein_sequence_found_in_many_input = True
                                record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)

                else:
                    raise ValueError('genome '+genome_name+' missing')

            SeqIO.write(records, many_forward_reads_file_path, "fasta")
            
        # Missing proper input_many_type
        #
        else:
            raise ValueError('Cannot yet handle input_many type of: '+type_name)            

        # check for failed input file creation
        #
        if params['input_one_name'] != None:
            if not protein_sequence_found_in_one_input:
                self.log(invalid_msgs,"no protein sequences found in '"+params['input_one_name']+"'")
        if not protein_sequence_found_in_many_input:
            self.log(invalid_msgs,"no protein sequences found in '"+params['input_many_name']+"'")


        # input data failed validation.  Need to return
        #
        if len(invalid_msgs) > 0:

            # load the method provenance from the context object
            #
            self.log(console,"SETTING PROVENANCE")  # DEBUG
            provenance = [{}]
            if 'provenance' in ctx:
                provenance = ctx['provenance']
            # add additional info to provenance here, in this case the input data object reference
            provenance[0]['input_ws_objects'] = []
            if 'input_one_name' in params and params['input_one_name'] != None:
                provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_one_name'])
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_many_name'])
            provenance[0]['service'] = 'kb_blast'
            provenance[0]['method'] = 'BLASTp_Search'


            # build output report object
            #
            self.log(console,"BUILDING REPORT")  # DEBUG
            report += "FAILURE:\n\n"+"\n".join(invalid_msgs)+"\n"
            reportObj = {
                'objects_created':[],
                'text_message':report
                }

            reportName = 'blast_report_'+str(hex(uuid.getnode()))
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            report_obj_info = ws.save_objects({
                    #'id':info[6],
                    'workspace':params['workspace_name'],
                    'objects':[
                        {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance  # DEBUG
                        }
                        ]
                    })[0]

            self.log(console,"BUILDING RETURN OBJECT")
            returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
            self.log(console,"BLASTp_Search DONE")
            return [returnVal]


        # FORMAT DB
        #
        # OLD SYNTAX: formatdb -i $database -o T -p F -> $database.nsq or $database.00.nsq
        # NEW SYNTAX: makeblastdb -in $database -parse_seqids -dbtype prot/nucl -out <basename>
        makeblastdb_cmd = [self.Make_BLAST_DB]

        # check for necessary files
        if not os.path.isfile(self.Make_BLAST_DB):
            raise ValueError("no such file '"+self.Make_BLAST_DB+"'")
        if not os.path.isfile(many_forward_reads_file_path):
            raise ValueError("no such file '"+many_forward_reads_file_path+"'")
        elif not os.path.getsize(many_forward_reads_file_path) > 0:
            raise ValueError("empty file '"+many_forward_reads_file_path+"'")

        makeblastdb_cmd.append('-in')
        makeblastdb_cmd.append(many_forward_reads_file_path)
        makeblastdb_cmd.append('-parse_seqids')
        makeblastdb_cmd.append('-dbtype')
        makeblastdb_cmd.append('prot')
        makeblastdb_cmd.append('-out')
        makeblastdb_cmd.append(many_forward_reads_file_path)

        # Run Make_BLAST_DB, capture output as it happens
        #
        self.log(console, 'RUNNING Make_BLAST_DB:')
        self.log(console, '    '+' '.join(makeblastdb_cmd))
#        report += "\n"+'running Make_BLAST_DB:'+"\n"
#        report += '    '+' '.join(makeblastdb_cmd)+"\n"

        p = subprocess.Popen(makeblastdb_cmd, \
                             cwd = self.scratch, \
                             stdout = subprocess.PIPE, \
                             stderr = subprocess.STDOUT, \
                             shell = False)

        while True:
            line = p.stdout.readline()
            if not line: break
            self.log(console, line.replace('\n', ''))

        p.stdout.close()
        p.wait()
        self.log(console, 'return code: ' + str(p.returncode))
        if p.returncode != 0:
            raise ValueError('Error running makeblastdb, return code: '+str(p.returncode) + 
                '\n\n'+ '\n'.join(console))

        # Check for db output
        if not os.path.isfile(many_forward_reads_file_path+".psq") and not os.path.isfile(many_forward_reads_file_path+".00.psq"):
            raise ValueError("makeblastdb failed to create DB file '"+many_forward_reads_file_path+".psq'")
        elif not os.path.getsize(many_forward_reads_file_path+".psq") > 0 and not os.path.getsize(many_forward_reads_file_path+".00.psq") > 0:
            raise ValueError("makeblastdb created empty DB file '"+many_forward_reads_file_path+".psq'")


        ### Construct the BLAST command
        #
        # OLD SYNTAX: $blast -q $q -G $G -E $E -m $m -e $e_value -v $limit -b $limit -K $limit -p blastp -i $fasta_file -d $database -o $out_file
        # NEW SYNTAX: blastp -query <queryfile> -db <basename> -out <out_aln_file> -outfmt 0/7 (8 became 7) -evalue <e_value> -dust no (DNA) -seg no (AA) -num_threads <num_cores>
        #
        blast_bin = self.BLASTp
        blast_cmd = [blast_bin]

        # check for necessary files
        if not os.path.isfile(blast_bin):
            raise ValueError("no such file '"+blast_bin+"'")
        if not os.path.isfile(one_forward_reads_file_path):
            raise ValueError("no such file '"+one_forward_reads_file_path+"'")
        elif not os.path.getsize(one_forward_reads_file_path) > 0:
            raise ValueError("empty file '"+one_forward_reads_file_path+"'")
        if not os.path.isfile(many_forward_reads_file_path):
            raise ValueError("no such file '"+many_forward_reads_file_path+"'")
        elif not os.path.getsize(many_forward_reads_file_path):
            raise ValueError("empty file '"+many_forward_reads_file_path+"'")

        # set the output path
        timestamp = int((datetime.utcnow() - datetime.utcfromtimestamp(0)).total_seconds()*1000)
        output_dir = os.path.join(self.scratch,'output.'+str(timestamp))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_aln_file_path = os.path.join(output_dir, 'alnout.txt');
        output_filtered_fasta_file_path = os.path.join(output_dir, 'output_filtered.fna');

        # this is command for basic search mode
        blast_cmd.append('-query')
        blast_cmd.append(one_forward_reads_file_path)
        blast_cmd.append('-db')
        blast_cmd.append(many_forward_reads_file_path)
        blast_cmd.append('-out')
        blast_cmd.append(output_aln_file_path)
        blast_cmd.append('-outfmt')
        blast_cmd.append('7')
        blast_cmd.append('-evalue')
        blast_cmd.append(str(params['e_value']))

        # options
        if 'maxaccepts' in params:
            if params['maxaccepts']:
                blast_cmd.append('-max_target_seqs')
                blast_cmd.append(str(params['maxaccepts']))

        # Run BLAST, capture output as it happens
        #
        self.log(console, 'RUNNING BLAST:')
        self.log(console, '    '+' '.join(blast_cmd))
#        report += "\n"+'running BLAST:'+"\n"
#        report += '    '+' '.join(blast_cmd)+"\n"

        p = subprocess.Popen(blast_cmd, \
                             cwd = self.scratch, \
                             stdout = subprocess.PIPE, \
                             stderr = subprocess.STDOUT, \
                             shell = False)

        while True:
            line = p.stdout.readline()
            if not line: break
            self.log(console, line.replace('\n', ''))

        p.stdout.close()
        p.wait()
        self.log(console, 'return code: ' + str(p.returncode))
        if p.returncode != 0:
            raise ValueError('Error running BLAST, return code: '+str(p.returncode) + 
                '\n\n'+ '\n'.join(console))


        # get query_len for filtering later
        #
        query_len = 0
        with open(one_forward_reads_file_path, 'r', 0) as query_file_handle:
            for line in query_file_handle:
                if line.startswith('>'):
                    continue
                query_len += len(re.sub(r" ","", line.rstrip())) 
        

        # Parse the BLAST tabular output and store ids to filter many set to make filtered object to save back to KBase
        #
        self.log(console, 'PARSING BLAST ALIGNMENT OUTPUT')
        if not os.path.isfile(output_aln_file_path):
            raise ValueError("failed to create BLAST output: "+output_aln_file_path)
        elif not os.path.getsize(output_aln_file_path) > 0:
            raise ValueError("created empty file for BLAST output: "+output_aln_file_path)
        hit_seq_ids = dict()
        output_aln_file_handle = open (output_aln_file_path, "r", 0)
        output_aln_buf = output_aln_file_handle.readlines()
        output_aln_file_handle.close()
        hit_total = 0
        high_bitscore_line = dict()
        high_bitscore_score = dict()
        high_bitscore_ident = dict()
        high_bitscore_alnlen = dict()
        hit_order = []
        hit_buf = []
        header_done = False
        for line in output_aln_buf:
            if line.startswith('#'):
                if not header_done:
                    hit_buf.append(line)
                continue
            header_done = True
            #self.log(console,'HIT LINE: '+line)  # DEBUG
            hit_info = line.split("\t")
            hit_seq_id     = hit_info[1]
            hit_ident      = float(hit_info[2]) / 100.0
            hit_aln_len    = hit_info[3]
            hit_mismatches = hit_info[4]
            hit_gaps       = hit_info[5]
            hit_q_beg      = hit_info[6]
            hit_q_end      = hit_info[7]
            hit_t_beg      = hit_info[8]
            hit_t_end      = hit_info[9]
            hit_e_value    = hit_info[10]
            hit_bitscore   = hit_info[11]

            # BLAST SOMETIMES ADDS THIS TO IDs.  NO IDEA WHY, BUT GET RID OF IT!
            if hit_seq_id.startswith('gnl|'):
                hit_seq_id = hit_seq_id[4:]

            try:
                if float(hit_bitscore) > float(high_bitscore_score[hit_seq_id]):
                    high_bitscore_score[hit_seq_id] = hit_bitscore
                    high_bitscore_ident[hit_seq_id] = hit_ident
                    high_bitscore_alnlen[hit_seq_id] = hit_aln_len
                    high_bitscore_line[hit_seq_id] = line
            except:
                hit_order.append(hit_seq_id)
                high_bitscore_score[hit_seq_id] = hit_bitscore
                high_bitscore_ident[hit_seq_id] = hit_ident
                high_bitscore_alnlen[hit_seq_id] = hit_aln_len
                high_bitscore_line[hit_seq_id] = line

        for hit_seq_id in hit_order:
            hit_buf.append(high_bitscore_line[hit_seq_id])

            #self.log(console,"HIT_SEQ_ID: '"+hit_seq_id+"'")
            if 'ident_thresh' in params and float(params['ident_thresh']) > float(high_bitscore_ident[hit_seq_id]):
                continue
            if 'bitscore' in params and float(params['bitscore']) > float(high_bitscore_score[hit_seq_id]):
                continue
            if 'overlap_fraction' in params and float(params['overlap_fraction']) > float(high_bitscore_alnlen[hit_seq_id])/float(query_len):
                continue
            
            hit_total += 1
            hit_seq_ids[hit_seq_id] = True
            self.log(console, "HIT: '"+hit_seq_id+"'")  # DEBUG
        

        self.log(console, 'EXTRACTING HITS FROM INPUT')
        self.log(console, 'MANY_TYPE_NAME: '+many_type_name)  # DEBUG


        # FeatureSet input -> FeatureSet output
        #
        if many_type_name == 'FeatureSet':

            seq_total = len(input_many_featureSet['elements'].keys())

            output_featureSet = dict()
            if 'description' in input_many_featureSet and input_many_featureSet['description'] != None:
                output_featureSet['description'] = input_many_featureSet['description'] + " - BLASTp_Search filtered"
            else:
                output_featureSet['description'] = "BLASTp_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()
            if 'element_ordering' in input_many_featureSet and input_many_featureSet['element_ordering'] != None:
                for fId in input_many_featureSet['element_ordering']:
                    try:
                        in_filtered_set = hit_seq_ids[fId]
                        #self.log(console, 'FOUND HIT '+fId)  # DEBUG
                        output_featureSet['element_ordering'].append(fId)
                        output_featureSet['elements'][fId] = input_many_featureSet['elements'][fId]
                    except:
                        pass
            else:
                fId_list = input_many_featureSet['elements'].keys()
                self.log(console,"ADDING FEATURES TO FEATURESET")
                for fId in sorted(fId_list):
                    try:
                        #self.log(console,"checking '"+fId+"'")
                        in_filtered_set = hit_seq_ids[fId]
                        #self.log(console, 'FOUND HIT '+fId)  # DEBUG
                        output_featureSet['element_ordering'].append(fId)
                        output_featureSet['elements'][fId] = input_many_featureSet['elements'][fId]
                    except:
                        pass

        # Parse Genome hits into FeatureSet
        #
        elif many_type_name == 'Genome':
            seq_total = 0

            output_featureSet = dict()
            if 'scientific_name' in input_many_genome and input_many_genome['scientific_name'] != None:
                output_featureSet['description'] = input_many_genome['scientific_name'] + " - BLASTp_Search filtered"
            else:
                output_featureSet['description'] = "BLASTp_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()
            for feature in input_many_genome['features']:
                seq_total += 1
                try:
                    in_filtered_set = hit_seq_ids[feature['id']]
                    #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
                    output_featureSet['element_ordering'].append(feature['id'])
                    output_featureSet['elements'][feature['id']] = [input_many_ref]
                except:
                    pass

        # Parse GenomeSet hits into FeatureSet
        #
        elif many_type_name == 'GenomeSet':
            seq_total = 0

            output_featureSet = dict()
            if 'description' in input_many_genomeSet and input_many_genomeSet['description'] != None:
                output_featureSet['description'] = input_many_genomeSet['description'] + " - BLASTp_Search filtered"
            else:
                output_featureSet['description'] = "BLASTp_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()

            for genome_name in input_many_genomeSet['elements'].keys():
                if 'ref' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['ref'] != None:
                    genomeRef = input_many_genomeSet['elements'][genome_name]['ref']
                    genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                    for feature in genome['features']:
                        seq_total += 1
                        try:
                            in_filtered_set = hit_seq_ids[feature['id']]
                            #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
                            output_featureSet['element_ordering'].append(feature['id'])
                            output_featureSet['elements'][feature['id']] = [genomeRef]
                        except:
                            pass

                elif 'data' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['data'] != None:
#                    genome = input_many_genomeSet['elements'][genome_name]['data']
#                    for feature in genome['features']:
#                        #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
#                        seq_total += 1
#                        try:
#                            in_filtered_set = hit_seq_ids[feature['id']]
#                            #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
#                            output_featureSet['element_ordering'].append(feature['id'])
                    raise ValueError ("FAILURE: unable to address genome object that is stored within 'data' field of genomeSet object")
#                            output_featureSet['elements'][feature['id']] = [genomeRef_is_inside_data_within_genomeSet_object_and_that_cant_be_addressed]
#                        except:
#                            pass


        # load the method provenance from the context object
        #
        self.log(console,"SETTING PROVENANCE")  # DEBUG
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects'] = []
        if 'input_one_name' in params and params['input_one_name'] != None:
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_one_name'])
        provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_many_name'])
        provenance[0]['service'] = 'kb_blast'
        provenance[0]['method'] = 'BLASTp_Search'


        # Upload results
        #
        if len(invalid_msgs) == 0:
            self.log(console,"UPLOADING RESULTS")  # DEBUG

            # input FeatureSet, Genome, and GenomeSet -> upload FeatureSet output
            new_obj_info = ws.save_objects({
                            'workspace': params['workspace_name'],
                            'objects':[{
                                    'type': 'KBaseCollections.FeatureSet',
                                    'data': output_featureSet,
                                    'name': params['output_filtered_name'],
                                    'meta': {},
                                    'provenance': provenance
                                }]
                        })

        # build output report object
        #
        self.log(console,"BUILDING REPORT")  # DEBUG
        if len(invalid_msgs) == 0:
            report += 'sequences in many set: '+str(seq_total)+"\n"
            report += 'sequences in hit set:  '+str(hit_total)+"\n"
            report += "\n"
            for line in hit_buf:
                report += line
            reportObj = {
                'objects_created':[{'ref':params['workspace_name']+'/'+params['output_filtered_name'], 'description':'BLASTp_Search hits'}],
                'text_message':report
                }
        else:
            report += "FAILURE\n\n"+"\n".join(invalid_msgs)+"\n"
            reportObj = {
                'objects_created':[],
                'text_message':report
                }

        reportName = 'blast_report_'+str(hex(uuid.getnode()))
        report_obj_info = ws.save_objects({
#                'id':info[6],
                'workspace':params['workspace_name'],
                'objects':[
                    {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance
                    }
                ]
            })[0]

        self.log(console,"BUILDING RETURN OBJECT")
#        returnVal = { 'output_report_name': reportName,
#                      'output_report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
#                      'output_filtered_ref': params['workspace_name']+'/'+params['output_filtered_name']
#                      }
        returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
        self.log(console,"BLASTp_Search DONE")
        #END BLASTp_Search

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method BLASTp_Search return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]


    def BLASTx_Search(self, ctx, params):
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN BLASTx_Search
        console = []
        invalid_msgs = []
        self.log(console,'Running BLASTx_Search with params=')
        self.log(console, "\n"+pformat(params))
        report = ''
#        report = 'Running BLASTx_Search with params='
#        report += "\n"+pformat(params)
        #protein_sequence_found_in_one_input = False
        protein_sequence_found_in_many_input = False


        #### do some basic checks
        #
        if 'workspace_name' not in params:
            raise ValueError('workspace_name parameter is required')
#        if 'input_one_name' not in params and 'input_one_sequence' not in params:
#            raise ValueError('input_one_sequence or input_one_name parameter is required')
        if 'input_one_name' not in params:
            raise ValueError('input_one_name parameter is required')
        if 'input_many_name' not in params:
            raise ValueError('input_many_name parameter is required')
        if 'output_filtered_name' not in params:
            raise ValueError('output_filtered_name parameter is required')


        # Write the input_one_sequence to a SingleEndLibrary object
        #
        if 'input_one_sequence' in params \
                and params['input_one_sequence'] != None \
                and params['input_one_sequence'] != "Optionally enter DNA sequence...":
            input_one_file_name = params['input_one_name']
            one_forward_reads_file_path = os.path.join(self.scratch,input_one_file_name)
            one_forward_reads_file_handle = open(one_forward_reads_file_path, 'w', 0)
            self.log(console, 'writing query reads file: '+str(one_forward_reads_file_path))

#            input_sequence_buf = params['input_one_sequence'].split("\n")
#            one_forward_reads_file_handle.write('>'+params['input_one_name']+"\n")
#            query_line_seen = False
#            for line in input_sequence_buf:
#                if not line.startswith('>'):
#                    one_forward_reads_file_handle.write(line+"\n")
#                else:
#                    if query_line_seen:
#                        break
#                    query_line_seen = True
#            one_forward_reads_file_handle.close();

            fastq_format = False
            input_sequence_buf = params['input_one_sequence']
            if input_sequence_buf.startswith('@'):
                fastq_format = True
                #self.log(console,"INPUT_SEQ BEFORE: '''\n"+input_sequence_buf+"\n'''")  # DEBUG
            input_sequence_buf = input_sequence_buf.strip()
            input_sequence_buf = re.sub ('&apos;', "'", input_sequence_buf)
            input_sequence_buf = re.sub ('&quot;', '"', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#39;',  "'", input_sequence_buf)
#        input_sequence_buf = re.sub ('&#34;',  '"', input_sequence_buf)
#        input_sequence_buf = re.sub ('&lt;;',  '<', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#60;',  '<', input_sequence_buf)
#        input_sequence_buf = re.sub ('&gt;',   '>', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#62;',  '>', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#36;',  '$', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#37;',  '%', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#47;',  '/', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#63;',  '?', input_sequence_buf)
##        input_sequence_buf = re.sub ('&#92;',  chr(92), input_sequence_buf)  # FIX LATER
#        input_sequence_buf = re.sub ('&#96;',  '`', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#124;', '|', input_sequence_buf)
#        input_sequence_buf = re.sub ('&amp;', '&', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#38;', '&', input_sequence_buf)
#        self.log(console,"INPUT_SEQ AFTER: '''\n"+input_sequence_buf+"\n'''")  # DEBUG

            DNA_pattern = re.compile("^[acgtuACGTU ]+$")
            space_pattern = re.compile("^[ \t]*$")
            split_input_sequence_buf = input_sequence_buf.split("\n")

            # no header rows, just sequence
            if not input_sequence_buf.startswith('>') and not input_sequence_buf.startswith('@'):
                one_forward_reads_file_handle.write('>'+params['input_one_name']+"\n")
                for line in split_input_sequence_buf:
                    if not space_pattern.match(line):
                        line = re.sub (" ","",line)
                        line = re.sub ("\t","",line)
                        if not DNA_pattern.match(line):
                            self.log(invalid_msgs,"BAD record:\n"+line+"\n")
                            continue
                        one_forward_reads_file_handle.write(line.lower()+"\n")
                one_forward_reads_file_handle.close()

            else:
                # format checks
                for i,line in enumerate(split_input_sequence_buf):
                    if line.startswith('>') or line.startswith('@'):
                        if not DNA_pattern.match(split_input_sequence_buf[i+1]):
                            if fastq_format:
                                bad_record = "\n".join([split_input_sequence_buf[i],
                                                        split_input_sequence_buf[i+1],
                                                        split_input_sequence_buf[i+2],
                                                        split_input_sequence_buf[i+3]])
                            else:
                                bad_record = "\n".join([split_input_sequence_buf[i],
                                                    split_input_sequence_buf[i+1]])
                            self.log(invalid_msgs,"BAD record:\n"+bad_record+"\n")
                        if fastq_format and line.startswith('@'):
                            format_ok = True
                            seq_len = len(split_input_sequence_buf[i+1])
                            if not seq_len > 0:
                                format_ok = False
                            if not split_input_sequence_buf[i+2].startswith('+'):
                                format_ok = False
                            if not seq_len == len(split_input_sequence_buf[i+3]):
                                format_ok = False
                            if not format_ok:
                                bad_record = "\n".join([split_input_sequence_buf[i],
                                                    split_input_sequence_buf[i+1],
                                                    split_input_sequence_buf[i+2],
                                                    split_input_sequence_buf[i+3]])
                                raise ValueError ("BAD record:\n"+bad_record+"\n")

                # write that sucker, removing spaces
                #
                #forward_reads_file_handle.write(input_sequence_buf)        input_sequence_buf = re.sub ('&quot;', '"', input_sequence_buf)
                for i,line in enumerate(split_input_sequence_buf):
                    if line.startswith('>'):
                        record_buf = []
                        record_buf.append(line)
                        for j in range(i+1,len(split_input_sequence_buf)):
                            if split_input_sequence_buf[j].startswith('>'):
                                break
                            seq_line = re.sub (" ","",split_input_sequence_buf[j])
                            seq_line = re.sub ("\t","",seq_line)
                            seq_line = seq_line.lower()
                            record_buf.append(seq_line)
                        record = "\n".join(record_buf)+"\n"
                        one_forward_reads_file_handle.write(record)
                        break  # only want first record
                    elif line.startswith('@'):
                        seq_line = re.sub (" ","",split_input_sequence_buf[i+1])
                        seq_line = re.sub ("\t","",seq_line)
                        seq_line = seq_line.lower()
                        qual_line = re.sub (" ","",split_input_sequence_buf[i+3])
                        qual_line = re.sub ("\t","",qual_line)
                        record = "\n".join([line, seq_line, split_input_sequence_buf[i+2], qual_line])+"\n"
                        one_forward_reads_file_handle.write(record)
                        break  # only want first record

                one_forward_reads_file_handle.close()


            # load the method provenance from the context object
            #
            self.log(console,"SETTING PROVENANCE")  # DEBUG
            provenance = [{}]
            if 'provenance' in ctx:
                provenance = ctx['provenance']
            # add additional info to provenance here, in this case the input data object reference
                provenance[0]['input_ws_objects'] = []
                provenance[0]['service'] = 'kb_blast'
                provenance[0]['method'] = 'BLASTx_Search'

                
                # Upload results
                #
                self.log(console,"UPLOADING QUERY OBJECT")  # DEBUG

                sequencing_tech = 'N/A'
                self.upload_SingleEndLibrary_to_shock_and_ws (ctx,
                                                      console,  # DEBUG
                                                      params['workspace_name'],
                                                      params['input_one_name'],
                                                      one_forward_reads_file_path,
                                                      provenance,
                                                      sequencing_tech
                                                      )

            self.log(console, 'done')

        #### Get the input_one object
        ##
        try:
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_one_name']}])
            data = objects[0]['data']
            info = objects[0]['info']
            # Object Info Contents
            # absolute ref = info[6] + '/' + info[0] + '/' + info[4]
            # 0 - obj_id objid
            # 1 - obj_name name
            # 2 - type_string type
            # 3 - timestamp save_date
            # 4 - int version
            # 5 - username saved_by
            # 6 - ws_id wsid
            # 7 - ws_name workspace
            # 8 - string chsum
            # 9 - int size 
            # 10 - usermeta meta
            one_type_name = info[2].split('.')[1].split('-')[0]
        except Exception as e:
            raise ValueError('Unable to fetch input_one_name object from workspace: ' + str(e))
        #to get the full stack trace: traceback.format_exc()

        if 'input_one_sequence' in params \
                and params['input_one_sequence'] != None \
                and params['input_one_sequence'] != "Optionally enter DNA sequence..." \
                and one_type_name != 'SingleEndLibrary':

            self.log(invalid_msgs,"ERROR: Mismatched input type for Query Object: "+params['input_one_name']+" should be SingleEndLibrary instead of: "+one_type_name)


        # Handle overloading (input_one can be Feature, SingleEndLibrary, or FeatureSet)
        #
        if one_type_name == 'SingleEndLibrary':
            try:
                if 'lib' in data:
                    one_forward_reads = data['lib']['file']
                elif 'handle' in data:
                    one_forward_reads = data['handle']
                else:
                    self.log(console,"bad structure for 'one_forward_reads'")
                    raise ValueError("bad structure for 'one_forward_reads'")

                ### NOTE: this section is what could be replaced by the transform services
                one_forward_reads_file_path = os.path.join(self.scratch,one_forward_reads['file_name'])
                one_forward_reads_file_handle = open(one_forward_reads_file_path, 'w', 0)
                self.log(console, 'downloading reads file: '+str(one_forward_reads_file_path))
                headers = {'Authorization': 'OAuth '+ctx['token']}
                r = requests.get(one_forward_reads['url']+'/node/'+one_forward_reads['id']+'?download', stream=True, headers=headers)
                for chunk in r.iter_content(1024):
                    one_forward_reads_file_handle.write(chunk)
                one_forward_reads_file_handle.close();
                self.log(console, 'done')
                ### END NOTE


                # remove carriage returns
                new_file_path = one_forward_reads_file_path+"-CRfree"
                new_file_handle = open(new_file_path, 'w', 0)
                one_forward_reads_file_handle = open(one_forward_reads_file_path, 'r', 0)
                for line in one_forward_reads_file_handle:
                    line = re.sub("\r","",line)
                    new_file_handle.write(line)
                one_forward_reads_file_handle.close();
                new_file_handle.close()
                one_forward_reads_file_path = new_file_path


                # convert FASTQ to FASTA (if necessary)
                new_file_path = one_forward_reads_file_path+".fna"
                new_file_handle = open(new_file_path, 'w', 0)
                one_forward_reads_file_handle = open(one_forward_reads_file_path, 'r', 0)
                header = None
                last_header = None
                last_seq_buf = None
                last_line_was_header = False
                was_fastq = False
                for line in one_forward_reads_file_handle:
                    if line.startswith('>'):
                        break
                    elif line.startswith('@'):
                        was_fastq = True
                        header = line[1:]
                        if last_header != None:
                            new_file_handle.write('>'+last_header)
                            new_file_handle.write(last_seq_buf)
                        last_seq_buf = None
                        last_header = header
                        last_line_was_header = True
                    elif last_line_was_header:
                        last_seq_buf = line
                        last_line_was_header = False
                    else:
                        continue
                if last_header != None:
                    new_file_handle.write('>'+last_header)
                    new_file_handle.write(last_seq_buf)

                new_file_handle.close()
                one_forward_reads_file_handle.close()
                if was_fastq:
                    one_forward_reads_file_path = new_file_path

            except Exception as e:
                print(traceback.format_exc())
                raise ValueError('Unable to download single-end read library files: ' + str(e))

        elif one_type_name == 'FeatureSet':
            # retrieve sequences for features
            input_one_featureSet = data
            
            genome2Features = {}
            features = input_one_featureSet['elements']

            if len(features.keys()) == 0:
                self.log(console,"No features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                self.log(invalid_msgs,"No features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
            if len(features.keys()) > 1:
                self.log(console,"Too many features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                self.log(invalid_msgs,"Too many features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))

            for fId in features.keys():
                genomeRef = features[fId][0]
                if genomeRef not in genome2Features:
                    genome2Features[genomeRef] = []
                genome2Features[genomeRef].append(fId)

            # export features to FASTA file
            one_forward_reads_file_path = os.path.join(self.scratch, params['input_one_name']+".fasta")
            self.log(console, 'writing fasta file: '+one_forward_reads_file_path)
            records = []
            for genomeRef in genome2Features:
                genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                these_genomeFeatureIds = genome2Features[genomeRef]
                for feature in genome['features']:
                    if feature['id'] in these_genomeFeatureIds:
                        # BLASTx is nuc-prot
                        if feature['type'] != 'CDS':
                            self.log(console,params['input_one_name']+" feature type must be CDS")
                            self.log(invalid_msgs,params['input_one_name']+" feature type must be CDS")
                        #elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                        #    self.log(console,"bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                        #    raise ValueError ("bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                        else:
                            record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genomeRef+"."+feature['id'])
                            #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genomeRef+"."+feature['id'])
                            records.append(record)
                            SeqIO.write(records, one_forward_reads_file_path, "fasta")
                            break  # only want first record

        elif one_type_name == 'Feature':
            # export feature to FASTA file
            feature = data
            one_forward_reads_file_path = os.path.join(self.scratch, params['input_one_name']+".fasta")
            self.log(console, 'writing fasta file: '+one_forward_reads_file_path)
            # BLASTx is nuc-prot
            if feature['type'] != 'CDS':
                self.log(console,params['input_one_name']+" feature type must be CDS")
                self.log(invalid_msgs,params['input_one_name']+" feature type must be CDS")
            #elif 'protein_translation' not in feature or feature['protein_translation'] == None:
            #    self.log(console,"bad CDS Feature "+params['input_one_name']+": no protein_translation found")
            #    raise ValueError ("bad CDS Feature "+params['input_one_name']+": no protein_translation found")
            else:
                record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genomeRef+"."+feature['id'])
                #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genomeRef+"."+feature['id'])
                SeqIO.write([record], one_forward_reads_file_path, "fasta")

        else:
            raise ValueError('Cannot yet handle input_one type of: '+type_name)            

        #### Get the input_many object
        ##
        try:
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_many_name']}])
            data = objects[0]['data']
            info = objects[0]['info']
            input_many_ref = str(info[6])+'/'+str(info[0])+'/'+str(info[4])
            many_type_name = info[2].split('.')[1].split('-')[0]

        except Exception as e:
            raise ValueError('Unable to fetch input_many_name object from workspace: ' + str(e))
            #to get the full stack trace: traceback.format_exc()

        # Handle overloading (input_many can be FeatureSet, Genome, or GenomeSet)
        #
        if many_type_name == 'FeatureSet':
            # retrieve sequences for features
            input_many_featureSet = data

            genome2Features = {}
            features = input_many_featureSet['elements']
            for fId in features.keys():
                genomeRef = features[fId][0]
                if genomeRef not in genome2Features:
                    genome2Features[genomeRef] = []
                genome2Features[genomeRef].append(fId)

            # export features to FASTA file
            many_forward_reads_file_path = os.path.join(self.scratch, params['input_many_name']+".fasta")
            self.log(console, 'writing fasta file: '+many_forward_reads_file_path)
            records = []
            feature_written = dict()
            for genomeRef in genome2Features:
                genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                these_genomeFeatureIds = genome2Features[genomeRef]
                for feature in genome['features']:
                    if feature['id'] in these_genomeFeatureIds:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG

                            # BLASTx is nuc-prot
                            if feature['type'] != 'CDS':
                                self.log(console,"skipping non-CDS feature "+feature['id'])
                                continue
                            elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                                self.log(console,"bad CDS feature "+feature['id'])
                                raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                protein_sequence_found_in_many_input = True
                                #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                                record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)
            SeqIO.write(records, many_forward_reads_file_path, "fasta")


        # Genome
        #
        elif many_type_name == 'Genome':
            input_many_genome = data
            many_forward_reads_file_dir = self.scratch
            many_forward_reads_file = params['input_many_name']+".fasta"

            many_forward_reads_file_path = self.KB_SDK_data2file_Genome2Fasta (
                genome_object = input_many_genome,
                file          = many_forward_reads_file,
                dir           = many_forward_reads_file_dir,
                console       = console,
                invalid_msgs  = invalid_msgs,
                residue_type  = 'protein',
                feature_type  = 'CDS',
                record_id_pattern = '%%feature_id%%',
                record_desc_pattern = '[%%genome_id%%]',
                case='upper',
                linewrap=50)

            protein_sequence_found_in_many_input = True  # FIX LATER


        # GenomeSet
        #
        elif many_type_name == 'GenomeSet':
            input_many_genomeSet = data

            # export features to FASTA file
            many_forward_reads_file_path = os.path.join(self.scratch, params['input_many_name']+".fasta")
            self.log(console, 'writing fasta file: '+many_forward_reads_file_path)

            records = []
            feature_written = dict()
            for genome_name in input_many_genomeSet['elements'].keys():
                if 'ref' in input_many_genomeSet['elements'][genome_name] and \
                         input_many_genomeSet['elements'][genome_name]['ref'] != None:
                    genome = ws.get_objects([{'ref': input_many_genomeSet['elements'][genome_name]['ref']}])[0]['data']
                    for feature in genome['features']:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG

                            # BLASTx is nuc-prot
                            if feature['type'] != 'CDS':
                                continue
                            elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                                self.log(console,"bad CDS feature "+feature['id'])
                                raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                protein_sequence_found_in_many_input = True
                                #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                                record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)

                elif 'data' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['data'] != None:
                    genome = input_many_genomeSet['elements'][genome_name]['data']
                    for feature in genome['features']:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG

                            # BLASTx is nuc-prot
                            if feature['type'] != 'CDS':
                                continue
                            elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                                self.log(console,"bad CDS feature "+feature['id'])
                                raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                protein_sequence_found_in_many_input = True
                                #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                                record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)

                else:
                    raise ValueError('genome '+genome_name+' missing')

            SeqIO.write(records, many_forward_reads_file_path, "fasta")
            
        # Missing proper input_many_type
        #
        else:
            raise ValueError('Cannot yet handle input_many type of: '+type_name)            

        # check for failed input file creation
        #
#        if not protein_sequence_found_in_one_input:
#            self.log(invalid_msgs,"no protein sequences found in '"+params['input_one_name']+"'")
        if not protein_sequence_found_in_many_input:
            self.log(invalid_msgs,"no protein sequences found in '"+params['input_many_name']+"'")


        # input data failed validation.  Need to return
        #
        if len(invalid_msgs) > 0:

            # load the method provenance from the context object
            #
            self.log(console,"SETTING PROVENANCE")  # DEBUG
            provenance = [{}]
            if 'provenance' in ctx:
                provenance = ctx['provenance']
            # add additional info to provenance here, in this case the input data object reference
            provenance[0]['input_ws_objects'] = []
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_one_name'])
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_many_name'])
            provenance[0]['service'] = 'kb_blast'
            provenance[0]['method'] = 'BLASTx_Search'


            # build output report object
            #
            self.log(console,"BUILDING REPORT")  # DEBUG
            report += "FAILURE:\n\n"+"\n".join(invalid_msgs)+"\n"
            reportObj = {
                'objects_created':[],
                'text_message':report
                }

            reportName = 'blast_report_'+str(hex(uuid.getnode()))
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            report_obj_info = ws.save_objects({
                    #'id':info[6],
                    'workspace':params['workspace_name'],
                    'objects':[
                        {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance  # DEBUG
                        }
                        ]
                    })[0]

            self.log(console,"BUILDING RETURN OBJECT")
            returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
            self.log(console,"BLASTx_Search DONE")
            return [returnVal]


        # FORMAT DB
        #
        # OLD SYNTAX: formatdb -i $database -o T -p F -> $database.nsq or $database.00.nsq
        # NEW SYNTAX: makeblastdb -in $database -parse_seqids -dbtype prot/nucl -out <basename>
        makeblastdb_cmd = [self.Make_BLAST_DB]

        # check for necessary files
        if not os.path.isfile(self.Make_BLAST_DB):
            raise ValueError("no such file '"+self.Make_BLAST_DB+"'")
        if not os.path.isfile(many_forward_reads_file_path):
            raise ValueError("no such file '"+many_forward_reads_file_path+"'")
        elif not os.path.getsize(many_forward_reads_file_path) > 0:
            raise ValueError("empty file '"+many_forward_reads_file_path+"'")

        makeblastdb_cmd.append('-in')
        makeblastdb_cmd.append(many_forward_reads_file_path)
        makeblastdb_cmd.append('-parse_seqids')
        makeblastdb_cmd.append('-dbtype')
        makeblastdb_cmd.append('prot')
        makeblastdb_cmd.append('-out')
        makeblastdb_cmd.append(many_forward_reads_file_path)

        # Run Make_BLAST_DB, capture output as it happens
        #
        self.log(console, 'RUNNING Make_BLAST_DB:')
        self.log(console, '    '+' '.join(makeblastdb_cmd))
#        report += "\n"+'running Make_BLAST_DB:'+"\n"
#        report += '    '+' '.join(makeblastdb_cmd)+"\n"

        p = subprocess.Popen(makeblastdb_cmd, \
                             cwd = self.scratch, \
                             stdout = subprocess.PIPE, \
                             stderr = subprocess.STDOUT, \
                             shell = False)

        while True:
            line = p.stdout.readline()
            if not line: break
            self.log(console, line.replace('\n', ''))

        p.stdout.close()
        p.wait()
        self.log(console, 'return code: ' + str(p.returncode))
        if p.returncode != 0:
            raise ValueError('Error running makeblastdb, return code: '+str(p.returncode) + 
                '\n\n'+ '\n'.join(console))

        # Check for db output
        if not os.path.isfile(many_forward_reads_file_path+".psq") and not os.path.isfile(many_forward_reads_file_path+".00.psq"):
            raise ValueError("makeblastdb failed to create DB file '"+many_forward_reads_file_path+".psq'")
        elif not os.path.getsize(many_forward_reads_file_path+".psq") > 0 and not os.path.getsize(many_forward_reads_file_path+".00.psq") > 0:
            raise ValueError("makeblastdb created empty DB file '"+many_forward_reads_file_path+".psq'")


        ### Construct the BLAST command
        #
        # OLD SYNTAX: $blast -q $q -G $G -E $E -m $m -e $e_value -v $limit -b $limit -K $limit -p blastx -i $fasta_file -d $database -o $out_file
        # NEW SYNTAX: blastx -query <queryfile> -db <basename> -out <out_aln_file> -outfmt 0/7 (8 became 7) -evalue <e_value> -dust no (DNA) -seg no (AA) -num_threads <num_cores>
        #
        blast_bin = self.BLASTx
        blast_cmd = [blast_bin]

        # check for necessary files
        if not os.path.isfile(blast_bin):
            raise ValueError("no such file '"+blast_bin+"'")
        if not os.path.isfile(one_forward_reads_file_path):
            raise ValueError("no such file '"+one_forward_reads_file_path+"'")
        elif not os.path.getsize(one_forward_reads_file_path) > 0:
            raise ValueError("empty file '"+one_forward_reads_file_path+"'")
        if not os.path.isfile(many_forward_reads_file_path):
            raise ValueError("no such file '"+many_forward_reads_file_path+"'")
        elif not os.path.getsize(many_forward_reads_file_path):
            raise ValueError("empty file '"+many_forward_reads_file_path+"'")

        # set the output path
        timestamp = int((datetime.utcnow() - datetime.utcfromtimestamp(0)).total_seconds()*1000)
        output_dir = os.path.join(self.scratch,'output.'+str(timestamp))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_aln_file_path = os.path.join(output_dir, 'alnout.txt');
        output_filtered_fasta_file_path = os.path.join(output_dir, 'output_filtered.fna');

        # this is command for basic search mode
        blast_cmd.append('-query')
        blast_cmd.append(one_forward_reads_file_path)
        blast_cmd.append('-db')
        blast_cmd.append(many_forward_reads_file_path)
        blast_cmd.append('-out')
        blast_cmd.append(output_aln_file_path)
        blast_cmd.append('-outfmt')
        blast_cmd.append('7')
        blast_cmd.append('-evalue')
        blast_cmd.append(str(params['e_value']))

        # options
        if 'maxaccepts' in params:
            if params['maxaccepts']:
                blast_cmd.append('-max_target_seqs')
                blast_cmd.append(str(params['maxaccepts']))

        # Run BLAST, capture output as it happens
        #
        self.log(console, 'RUNNING BLAST:')
        self.log(console, '    '+' '.join(blast_cmd))
#        report += "\n"+'running BLAST:'+"\n"
#        report += '    '+' '.join(blast_cmd)+"\n"

        p = subprocess.Popen(blast_cmd, \
                             cwd = self.scratch, \
                             stdout = subprocess.PIPE, \
                             stderr = subprocess.STDOUT, \
                             shell = False)

        while True:
            line = p.stdout.readline()
            if not line: break
            self.log(console, line.replace('\n', ''))

        p.stdout.close()
        p.wait()
        self.log(console, 'return code: ' + str(p.returncode))
        if p.returncode != 0:
            raise ValueError('Error running BLAST, return code: '+str(p.returncode) + 
                '\n\n'+ '\n'.join(console))


        # get query_len for filtering later
        #
        query_len = 0
        with open(one_forward_reads_file_path, 'r', 0) as query_file_handle:
            for line in query_file_handle:
                if line.startswith('>'):
                    continue
                query_len += len(re.sub(r" ","", line.rstrip())) 
        query_len = query_len/3.0  # BLASTx is nuc-prot

                
        # Parse the BLAST tabular output and store ids to filter many set to make filtered object to save back to KBase
        #
        self.log(console, 'PARSING BLAST ALIGNMENT OUTPUT')
        if not os.path.isfile(output_aln_file_path):
            raise ValueError("failed to create BLAST output: "+output_aln_file_path)
        elif not os.path.getsize(output_aln_file_path) > 0:
            raise ValueError("created empty file for BLAST output: "+output_aln_file_path)
        hit_seq_ids = dict()
        output_aln_file_handle = open (output_aln_file_path, "r", 0)
        output_aln_buf = output_aln_file_handle.readlines()
        output_aln_file_handle.close()
        hit_total = 0
        high_bitscore_line = dict()
        high_bitscore_score = dict()
        high_bitscore_ident = dict()
        high_bitscore_alnlen = dict()
        hit_order = []
        hit_buf = []
        header_done = False
        for line in output_aln_buf:
            if line.startswith('#'):
                if not header_done:
                    hit_buf.append(line)
                continue
            header_done = True
            #self.log(console,'HIT LINE: '+line)  # DEBUG
            hit_info = line.split("\t")
            hit_seq_id     = hit_info[1]
            hit_ident      = float(hit_info[2]) / 100.0
            hit_aln_len    = hit_info[3]
            hit_mismatches = hit_info[4]
            hit_gaps       = hit_info[5]
            hit_q_beg      = hit_info[6]
            hit_q_end      = hit_info[7]
            hit_t_beg      = hit_info[8]
            hit_t_end      = hit_info[9]
            hit_e_value    = hit_info[10]
            hit_bitscore   = hit_info[11]

            # BLAST SOMETIMES ADDS THIS TO IDs.  NO IDEA WHY, BUT GET RID OF IT!
            if hit_seq_id.startswith('gnl|'):
                hit_seq_id = hit_seq_id[4:]

            try:
                if float(hit_bitscore) > float(high_bitscore_score[hit_seq_id]):
                    high_bitscore_score[hit_seq_id] = hit_bitscore
                    high_bitscore_ident[hit_seq_id] = hit_ident
                    high_bitscore_alnlen[hit_seq_id] = hit_aln_len
                    high_bitscore_line[hit_seq_id] = line
            except:
                hit_order.append(hit_seq_id)
                high_bitscore_score[hit_seq_id] = hit_bitscore
                high_bitscore_ident[hit_seq_id] = hit_ident
                high_bitscore_alnlen[hit_seq_id] = hit_aln_len
                high_bitscore_line[hit_seq_id] = line

        for hit_seq_id in hit_order:
            hit_buf.append(high_bitscore_line[hit_seq_id])

            #self.log(console,"HIT_SEQ_ID: '"+hit_seq_id+"'")
            if 'ident_thresh' in params and float(params['ident_thresh']) > float(high_bitscore_ident[hit_seq_id]):
                continue
            if 'bitscore' in params and float(params['bitscore']) > float(high_bitscore_score[hit_seq_id]):
                continue
            if 'overlap_fraction' in params and float(params['overlap_fraction']) > float(high_bitscore_alnlen[hit_seq_id])/float(query_len):
                continue
            
            hit_total += 1
            hit_seq_ids[hit_seq_id] = True
            self.log(console, "HIT: '"+hit_seq_id+"'")  # DEBUG
        

        self.log(console, 'EXTRACTING HITS FROM INPUT')
        self.log(console, 'MANY_TYPE_NAME: '+many_type_name)  # DEBUG


        # FeatureSet input -> FeatureSet output
        #
        if many_type_name == 'FeatureSet':

            seq_total = len(input_many_featureSet['elements'].keys())

            output_featureSet = dict()
            if 'description' in input_many_featureSet and input_many_featureSet['description'] != None:
                output_featureSet['description'] = input_many_featureSet['description'] + " - BLASTx_Search filtered"
            else:
                output_featureSet['description'] = "BLASTx_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()
            if 'element_ordering' in input_many_featureSet and input_many_featureSet['element_ordering'] != None:
                for fId in input_many_featureSet['element_ordering']:
                    try:
                        in_filtered_set = hit_seq_ids[fId]
                        #self.log(console, 'FOUND HIT '+fId)  # DEBUG
                        output_featureSet['element_ordering'].append(fId)
                        output_featureSet['elements'][fId] = input_many_featureSet['elements'][fId]
                    except:
                        pass
            else:
                fId_list = input_many_featureSet['elements'].keys()
                self.log(console,"ADDING FEATURES TO FEATURESET")
                for fId in sorted(fId_list):
                    try:
                        #self.log(console,"checking '"+fId+"'")
                        in_filtered_set = hit_seq_ids[fId]
                        #self.log(console, 'FOUND HIT '+fId)  # DEBUG
                        output_featureSet['element_ordering'].append(fId)
                        output_featureSet['elements'][fId] = input_many_featureSet['elements'][fId]
                    except:
                        pass

        # Parse Genome hits into FeatureSet
        #
        elif many_type_name == 'Genome':
            seq_total = 0

            output_featureSet = dict()
            if 'scientific_name' in input_many_genome and input_many_genome['scientific_name'] != None:
                output_featureSet['description'] = input_many_genome['scientific_name'] + " - BLASTx_Search filtered"
            else:
                output_featureSet['description'] = "BLASTx_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()
            for feature in input_many_genome['features']:
                seq_total += 1
                try:
                    in_filtered_set = hit_seq_ids[feature['id']]
                    #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
                    output_featureSet['element_ordering'].append(feature['id'])
                    output_featureSet['elements'][feature['id']] = [input_many_ref]
                except:
                    pass

        # Parse GenomeSet hits into FeatureSet
        #
        elif many_type_name == 'GenomeSet':
            seq_total = 0

            output_featureSet = dict()
            if 'description' in input_many_genomeSet and input_many_genomeSet['description'] != None:
                output_featureSet['description'] = input_many_genomeSet['description'] + " - BLASTx_Search filtered"
            else:
                output_featureSet['description'] = "BLASTx_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()

            for genome_name in input_many_genomeSet['elements'].keys():
                if 'ref' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['ref'] != None:
                    genomeRef = input_many_genomeSet['elements'][genome_name]['ref']
                    genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                    for feature in genome['features']:
                        seq_total += 1
                        try:
                            in_filtered_set = hit_seq_ids[feature['id']]
                            #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
                            output_featureSet['element_ordering'].append(feature['id'])
                            output_featureSet['elements'][feature['id']] = [genomeRef]
                        except:
                            pass

                elif 'data' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['data'] != None:
#                    genome = input_many_genomeSet['elements'][genome_name]['data']
#                    for feature in genome['features']:
#                        #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
#                        seq_total += 1
#                        try:
#                            in_filtered_set = hit_seq_ids[feature['id']]
#                            #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
#                            output_featureSet['element_ordering'].append(feature['id'])
                    raise ValueError ("FAILURE: unable to address genome object that is stored within 'data' field of genomeSet object")
#                            output_featureSet['elements'][feature['id']] = [genomeRef_is_inside_data_within_genomeSet_object_and_that_cant_be_addressed]
#                        except:
#                            pass


        # load the method provenance from the context object
        #
        self.log(console,"SETTING PROVENANCE")  # DEBUG
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects'] = []
        if 'input_one_name' in params and params['input_one_name'] != None:
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_one_name'])
        provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_many_name'])
        provenance[0]['service'] = 'kb_blast'
        provenance[0]['method'] = 'BLASTx_Search'


        # Upload results
        #
        if len(invalid_msgs) == 0:
            self.log(console,"UPLOADING RESULTS")  # DEBUG

            # input FeatureSet, Genome, and GenomeSet -> upload FeatureSet output
            new_obj_info = ws.save_objects({
                            'workspace': params['workspace_name'],
                            'objects':[{
                                    'type': 'KBaseCollections.FeatureSet',
                                    'data': output_featureSet,
                                    'name': params['output_filtered_name'],
                                    'meta': {},
                                    'provenance': provenance
                                }]
                        })

        # build output report object
        #
        self.log(console,"BUILDING REPORT")  # DEBUG
        if len(invalid_msgs) == 0:
            report += 'sequences in many set: '+str(seq_total)+"\n"
            report += 'sequences in hit set:  '+str(hit_total)+"\n"
            report += "\n"
            for line in hit_buf:
                report += line
            reportObj = {
                'objects_created':[{'ref':params['workspace_name']+'/'+params['output_filtered_name'], 'description':'BLASTx_Search hits'}],
                'text_message':report
                }
        else:
            report += "FAILURE\n\n"+"\n".join(invalid_msgs)+"\n"
            reportObj = {
                'objects_created':[],
                'text_message':report
                }
            
        reportName = 'blast_report_'+str(hex(uuid.getnode()))
        report_obj_info = ws.save_objects({
#                'id':info[6],
                'workspace':params['workspace_name'],
                'objects':[
                    {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance
                    }
                ]
            })[0]

        self.log(console,"BUILDING RETURN OBJECT")
#        returnVal = { 'output_report_name': reportName,
#                      'output_report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
#                      'output_filtered_ref': params['workspace_name']+'/'+params['output_filtered_name']
#                      }
        returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
        self.log(console,"BLASTx_Search DONE")
        #END BLASTx_Search

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method BLASTx_Search return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]


    def tBLASTn_Search(self, ctx, params):
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN tBLASTn_Search
        console = []
        invalid_msgs = []
        self.log(console,'Running tBLASTn_Search with params=')
        self.log(console, "\n"+pformat(params))
        report = ''
#        report = 'Running tBLASTn_Search with params='
#        report += "\n"+pformat(params)
        protein_sequence_found_in_one_input = False
        #protein_sequence_found_in_many_input = False


        #### do some basic checks
        #
        if 'workspace_name' not in params:
            raise ValueError('workspace_name parameter is required')
#        if 'input_one_name' not in params and 'input_one_sequence' not in params:
#            raise ValueError('input_one_sequence or input_one_name parameter is required')
        if 'input_one_name' not in params:
            raise ValueError('input_one_name parameter is required')
        if 'input_many_name' not in params:
            raise ValueError('input_many_name parameter is required')
        if 'output_filtered_name' not in params:
            raise ValueError('output_filtered_name parameter is required')



        # Write the input_one_sequence to file
        #
        if 'input_one_sequence' in params \
                and params['input_one_sequence'] != None \
                and params['input_one_sequence'] != "Optionally enter PROTEIN sequence...":
            #input_one_file_name = params['input_one_name']
            input_one_name = 'query.faa'
            input_one_file_name = input_one_name
            one_forward_reads_file_path = os.path.join(self.scratch,input_one_file_name)
            one_forward_reads_file_handle = open(one_forward_reads_file_path, 'w', 0)
            self.log(console, 'writing query reads file: '+str(one_forward_reads_file_path))

#            input_sequence_buf = params['input_one_sequence'].split("\n")
#            one_forward_reads_file_handle.write('>'+params['input_one_name']+"\n")
#            query_line_seen = False
#            for line in input_sequence_buf:
#                if not line.startswith('>'):
#                    one_forward_reads_file_handle.write(line+"\n")
#                else:
#                    if query_line_seen:
#                        break
#                    query_line_seen = True
#            one_forward_reads_file_handle.close();

            input_sequence_buf = params['input_one_sequence']
            input_sequence_buf = input_sequence_buf.strip()
            space_pattern = re.compile("^[ \t]*$")
            split_input_sequence_buf = input_sequence_buf.split("\n")

            # no header rows, just sequence
            if not input_sequence_buf.startswith('>'):
                one_forward_reads_file_handle.write('>'+input_one_name+"\n")
                for line in split_input_sequence_buf:
                    if not space_pattern.match(line):
                        line = re.sub (" ","",line)
                        line = re.sub ("\t","",line)
                        one_forward_reads_file_handle.write(line.upper()+"\n")
                one_forward_reads_file_handle.close()

            else:
                # write that sucker, removing spaces
                #
                #forward_reads_file_handle.write(input_sequence_buf)        input_sequence_buf = re.sub ('&quot;', '"', input_sequence_buf)
                for i,line in enumerate(split_input_sequence_buf):
                    if line.startswith('>'):
                        record_buf = []
                        record_buf.append(line)
                        for j in range(i+1,len(split_input_sequence_buf)):
                            if split_input_sequence_buf[j].startswith('>'):
                                break
                            seq_line = re.sub (" ","",split_input_sequence_buf[j])
                            seq_line = re.sub ("\t","",seq_line)
                            seq_line = seq_line.upper()
                            record_buf.append(seq_line)
                        record = "\n".join(record_buf)+"\n"
                        one_forward_reads_file_handle.write(record)
                        break  # only want first record
                one_forward_reads_file_handle.close()


        #### Get the input_one object
        ##
        elif 'input_one_name' in params and params['input_one_name'] != None:
            try:
                ws = workspaceService(self.workspaceURL, token=ctx['token'])
                objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_one_name']}])
                data = objects[0]['data']
                info = objects[0]['info']
                # Object Info Contents
                # absolute ref = info[6] + '/' + info[0] + '/' + info[4]
                # 0 - obj_id objid
                # 1 - obj_name name
                # 2 - type_string type
                # 3 - timestamp save_date
                # 4 - int version
                # 5 - username saved_by
                # 6 - ws_id wsid
                # 7 - ws_name workspace
                # 8 - string chsum
                # 9 - int size 
                # 10 - usermeta meta
                one_type_name = info[2].split('.')[1].split('-')[0]
            except Exception as e:
                raise ValueError('Unable to fetch input_one_name object from workspace: ' + str(e))
                #to get the full stack trace: traceback.format_exc()


            # Handle overloading (input_one can be Feature, or FeatureSet)
            #
            if one_type_name == 'FeatureSet':
                # retrieve sequences for features
                input_one_featureSet = data
            
                genome2Features = {}
                features = input_one_featureSet['elements']

                if len(features.keys()) == 0:
                    self.log(console,"No features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                    self.log(invalid_msgs,"No features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                if len(features.keys()) > 1:
                    self.log(console,"Too many features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                    self.log(invalid_msgs,"Too many features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))

                for fId in features.keys():
                    genomeRef = features[fId][0]
                    if genomeRef not in genome2Features:
                        genome2Features[genomeRef] = []
                    genome2Features[genomeRef].append(fId)

                # export features to FASTA file
                one_forward_reads_file_path = os.path.join(self.scratch, params['input_one_name']+".fasta")
                self.log(console, 'writing fasta file: '+one_forward_reads_file_path)
                records = []
                for genomeRef in genome2Features:
                    genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                    these_genomeFeatureIds = genome2Features[genomeRef]
                    for feature in genome['features']:
                        if feature['id'] in these_genomeFeatureIds:
                            # tBLASTn is prot-nuc
                            #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genomeRef+"."+feature['id'])
                            if feature['type'] != 'CDS':
                                self.log(console,params['input_one_name']+" feature type must be CDS")
                                self.log(invalid_msgs,params['input_one_name']+" feature type must be CDS")
                            elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                                self.log(console,"bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                                raise ValueError ("bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                            else:
                                protein_sequence_found_in_one_input = True
                                record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genomeRef+"."+feature['id'])
                                records.append(record)
                                SeqIO.write(records, one_forward_reads_file_path, "fasta")
                                break  # only want first record

            elif one_type_name == 'Feature':
                # export feature to FASTA file
                feature = data
                one_forward_reads_file_path = os.path.join(self.scratch, params['input_one_name']+".fasta")
                self.log(console, 'writing fasta file: '+one_forward_reads_file_path)
                # tBLASTn is prot-nuc
                #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description='['+feature['genome_id']+']'+' '+feature['function'])
                if feature['type'] != 'CDS':
                    self.log(console,params['input_one_name']+" feature type must be CDS")
                    self.log(invalid_msgs,params['input_one_name']+" feature type must be CDS")
                elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                    self.log(console,"bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                    raise ValueError ("bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                else:
                    protein_sequence_found_in_one_input = True
                    record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genomeRef+"."+feature['id'])
                    SeqIO.write([record], one_forward_reads_file_path, "fasta")

            else:
                raise ValueError('Cannot yet handle input_one type of: '+type_name)            
        else:
            raise ValueError('Must define either input_one_sequence or input_one_name')


        #### Get the input_many object
        ##
        many_forward_reads_file_compression = None
        sequencing_tech = 'N/A'
        try:
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_many_name']}])
            data = objects[0]['data']
            info = objects[0]['info']
            input_many_ref = str(info[6])+'/'+str(info[0])+'/'+str(info[4])
            many_type_name = info[2].split('.')[1].split('-')[0]

            if many_type_name == 'SingleEndLibrary':
                many_type_namespace = info[2].split('.')[0]
                if many_type_namespace == 'KBaseAssembly':
                    file_name = data['handle']['file_name']
                elif many_type_namespace == 'KBaseFile':
                    file_name = data['lib']['file']['file_name']
                else:
                    raise ValueError('bad data type namespace: '+many_type_namespace)
                #self.log(console, 'INPUT_MANY_FILENAME: '+file_name)  # DEBUG
                if file_name[-3:] == ".gz":
                    many_forward_reads_file_compression = 'gz'
                if 'sequencing_tech' in data:
                    sequencing_tech = data['sequencing_tech']

        except Exception as e:
            raise ValueError('Unable to fetch input_many_name object from workspace: ' + str(e))
            #to get the full stack trace: traceback.format_exc()

        # Handle overloading (input_many can be SingleEndLibrary, FeatureSet, Genome, or GenomeSet)
        #
        if many_type_name == 'SingleEndLibrary':

            # DEBUG
            #for k in data:
            #    self.log(console,"SingleEndLibrary ["+k+"]: "+str(data[k]))

            try:
                if 'lib' in data:
                    many_forward_reads = data['lib']['file']
                elif 'handle' in data:
                    many_forward_reads = data['handle']
                else:
                    self.log(console,"bad structure for 'many_forward_reads'")
                    raise ValueError("bad structure for 'many_forward_reads'")
                #if 'lib2' in data:
                #    reverse_reads = data['lib2']['file']
                #elif 'handle_2' in data:
                #    reverse_reads = data['handle_2']
                #else:
                #    reverse_reads={}

                ### NOTE: this section is what could be replaced by the transform services
                many_forward_reads_file_path = os.path.join(self.scratch,many_forward_reads['file_name'])
                many_forward_reads_file_handle = open(many_forward_reads_file_path, 'w', 0)
                self.log(console, 'downloading reads file: '+str(many_forward_reads_file_path))
                headers = {'Authorization': 'OAuth '+ctx['token']}
                r = requests.get(many_forward_reads['url']+'/node/'+many_forward_reads['id']+'?download', stream=True, headers=headers)
                for chunk in r.iter_content(1024):
                    many_forward_reads_file_handle.write(chunk)
                many_forward_reads_file_handle.close();
                self.log(console, 'done')
                ### END NOTE


                # remove carriage returns
                new_file_path = many_forward_reads_file_path+"-CRfree"
                new_file_handle = open(new_file_path, 'w', 0)
                many_forward_reads_file_handle = open(many_forward_reads_file_path, 'r', 0)
                for line in many_forward_reads_file_handle:
                    line = re.sub("\r","",line)
                    new_file_handle.write(line)
                many_forward_reads_file_handle.close();
                new_file_handle.close()
                many_forward_reads_file_path = new_file_path


                # convert FASTQ to FASTA (if necessary)
                new_file_path = many_forward_reads_file_path+".fna"
                new_file_handle = open(new_file_path, 'w', 0)
                if many_forward_reads_file_compression == 'gz':
                    many_forward_reads_file_handle = gzip.open(many_forward_reads_file_path, 'r', 0)
                else:
                    many_forward_reads_file_handle = open(many_forward_reads_file_path, 'r', 0)
                header = None
                last_header = None
                last_seq_buf = None
                last_line_was_header = False
                was_fastq = False
                for line in many_forward_reads_file_handle:
                    if line.startswith('>'):
                        break
                    elif line.startswith('@'):
                        was_fastq = True
                        header = line[1:]
                        if last_header != None:
                            new_file_handle.write('>'+last_header)
                            new_file_handle.write(last_seq_buf)
                        last_seq_buf = None
                        last_header = header
                        last_line_was_header = True
                    elif last_line_was_header:
                        last_seq_buf = line
                        last_line_was_header = False
                    else:
                        continue
                if last_header != None:
                    new_file_handle.write('>'+last_header)
                    new_file_handle.write(last_seq_buf)

                new_file_handle.close()
                many_forward_reads_file_handle.close()
                if was_fastq:
                    many_forward_reads_file_path = new_file_path

            except Exception as e:
                print(traceback.format_exc())
                raise ValueError('Unable to download single-end read library files: ' + str(e))

        # FeatureSet
        #
        elif many_type_name == 'FeatureSet':
            # retrieve sequences for features
            input_many_featureSet = data

            genome2Features = {}
            features = input_many_featureSet['elements']
            for fId in features.keys():
                genomeRef = features[fId][0]
                if genomeRef not in genome2Features:
                    genome2Features[genomeRef] = []
                genome2Features[genomeRef].append(fId)

            # export features to FASTA file
            many_forward_reads_file_path = os.path.join(self.scratch, params['input_many_name']+".fasta")
            self.log(console, 'writing fasta file: '+many_forward_reads_file_path)
            records = []
            feature_written = dict()
            for genomeRef in genome2Features:
                genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                these_genomeFeatureIds = genome2Features[genomeRef]
                for feature in genome['features']:
                    if feature['id'] in these_genomeFeatureIds:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG

                            # tBLASTn is prot-nuc
                            if feature['type'] != 'CDS':
                                self.log(console,params['input_many_name']+" features must all be CDS type")
                                continue
                            #elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                            #    self.log(console,"bad CDS feature "+feature['id'])
                            #    raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                                #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)
            SeqIO.write(records, many_forward_reads_file_path, "fasta")


        # Genome
        #
        elif many_type_name == 'Genome':
            input_many_genome = data
            many_forward_reads_file_dir = self.scratch
            many_forward_reads_file = params['input_many_name']+".fasta"

            many_forward_reads_file_path = self.KB_SDK_data2file_Genome2Fasta (
                genome_object = input_many_genome,
                file          = many_forward_reads_file,
                dir           = many_forward_reads_file_dir,
                console       = console,
                invalid_msgs  = invalid_msgs,
                residue_type  = 'nucleotide',
                feature_type  = 'CDS',
                record_id_pattern = '%%feature_id%%',
                record_desc_pattern = '[%%genome_id%%]',
                case='upper',
                linewrap=50)


        # GenomeSet
        #
        elif many_type_name == 'GenomeSet':
            input_many_genomeSet = data

            # export features to FASTA file
            many_forward_reads_file_path = os.path.join(self.scratch, params['input_many_name']+".fasta")
            self.log(console, 'writing fasta file: '+many_forward_reads_file_path)

            records = []
            feature_written = dict()
            for genome_name in input_many_genomeSet['elements'].keys():
                if 'ref' in input_many_genomeSet['elements'][genome_name] and \
                         input_many_genomeSet['elements'][genome_name]['ref'] != None:
                    genome = ws.get_objects([{'ref': input_many_genomeSet['elements'][genome_name]['ref']}])[0]['data']
                    for feature in genome['features']:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG

                            # tBLASTn is prot-nuc
                            if feature['type'] != 'CDS':
                                self.log(console,params['input_many_name']+" features must all be CDS type")
                                continue
                            #elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                            #    self.log(console,"bad CDS feature "+feature['id'])
                            #    raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                                #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)

                elif 'data' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['data'] != None:
                    genome = input_many_genomeSet['elements'][genome_name]['data']
                    for feature in genome['features']:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG

                            # tBLASTn is prot-nuc
                            if feature['type'] != 'CDS':
                                self.log(console,params['input_many_name']+" features must all be CDS type")
                                continue
                            #elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                            #    self.log(console,"bad CDS feature "+feature['id'])
                            #    raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                                #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)

                else:
                    raise ValueError('genome '+genome_name+' missing')

            SeqIO.write(records, many_forward_reads_file_path, "fasta")
            
        # Missing proper input_many_type
        #
        else:
            raise ValueError('Cannot yet handle input_many type of: '+type_name)            

        # check for failed input file creation
        #
        if params['input_one_name'] != None:
            if not protein_sequence_found_in_one_input:
                self.log(invalid_msgs,"no protein sequences found in '"+params['input_one_name']+"'")
#        if not protein_sequence_found_in_many_input:
#            self.log(invalid_msgs,"no protein sequences found in '"+params['input_many_name']+"'")


        # input data failed validation.  Need to return
        #
        if len(invalid_msgs) > 0:

            # load the method provenance from the context object
            #
            self.log(console,"SETTING PROVENANCE")  # DEBUG
            provenance = [{}]
            if 'provenance' in ctx:
                provenance = ctx['provenance']
            # add additional info to provenance here, in this case the input data object reference
            provenance[0]['input_ws_objects'] = []
            if 'input_one_name' in params and params['input_one_name'] != None:
                provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_one_name'])
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_many_name'])
            provenance[0]['service'] = 'kb_blast'
            provenance[0]['method'] = 'tBLASTn_Search'


            # build output report object
            #
            self.log(console,"BUILDING REPORT")  # DEBUG
            report += "FAILURE:\n\n"+"\n".join(invalid_msgs)+"\n"
            reportObj = {
                'objects_created':[],
                'text_message':report
                }

            reportName = 'blast_report_'+str(hex(uuid.getnode()))
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            report_obj_info = ws.save_objects({
                    #'id':info[6],
                    'workspace':params['workspace_name'],
                    'objects':[
                        {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance  # DEBUG
                        }
                        ]
                    })[0]

            self.log(console,"BUILDING RETURN OBJECT")
            returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
            self.log(console,"tBLASTn_Search DONE")
            return [returnVal]


        # FORMAT DB
        #
        # OLD SYNTAX: formatdb -i $database -o T -p F -> $database.nsq or $database.00.nsq
        # NEW SYNTAX: makeblastdb -in $database -parse_seqids -dbtype prot/nucl -out <basename>
        makeblastdb_cmd = [self.Make_BLAST_DB]

        # check for necessary files
        if not os.path.isfile(self.Make_BLAST_DB):
            raise ValueError("no such file '"+self.Make_BLAST_DB+"'")
        if not os.path.isfile(many_forward_reads_file_path):
            raise ValueError("no such file '"+many_forward_reads_file_path+"'")
        elif not os.path.getsize(many_forward_reads_file_path) > 0:
            raise ValueError("empty file '"+many_forward_reads_file_path+"'")

        makeblastdb_cmd.append('-in')
        makeblastdb_cmd.append(many_forward_reads_file_path)
        makeblastdb_cmd.append('-parse_seqids')
        makeblastdb_cmd.append('-dbtype')
        makeblastdb_cmd.append('nucl')
        makeblastdb_cmd.append('-out')
        makeblastdb_cmd.append(many_forward_reads_file_path)

        # Run Make_BLAST_DB, capture output as it happens
        #
        self.log(console, 'RUNNING Make_BLAST_DB:')
        self.log(console, '    '+' '.join(makeblastdb_cmd))
#        report += "\n"+'running Make_BLAST_DB:'+"\n"
#        report += '    '+' '.join(makeblastdb_cmd)+"\n"

        p = subprocess.Popen(makeblastdb_cmd, \
                             cwd = self.scratch, \
                             stdout = subprocess.PIPE, \
                             stderr = subprocess.STDOUT, \
                             shell = False)

        while True:
            line = p.stdout.readline()
            if not line: break
            self.log(console, line.replace('\n', ''))

        p.stdout.close()
        p.wait()
        self.log(console, 'return code: ' + str(p.returncode))
        if p.returncode != 0:
            raise ValueError('Error running makeblastdb, return code: '+str(p.returncode) + 
                '\n\n'+ '\n'.join(console))

        # Check for db output
        if not os.path.isfile(many_forward_reads_file_path+".nsq") and not os.path.isfile(many_forward_reads_file_path+".00.nsq"):
            raise ValueError("makeblastdb failed to create DB file '"+many_forward_reads_file_path+".nsq'")
        elif not os.path.getsize(many_forward_reads_file_path+".nsq") > 0 and not os.path.getsize(many_forward_reads_file_path+".00.nsq") > 0:
            raise ValueError("makeblastdb created empty DB file '"+many_forward_reads_file_path+".nsq'")


        ### Construct the BLAST command
        #
        # OLD SYNTAX: $blast -q $q -G $G -E $E -m $m -e $e_value -v $limit -b $limit -K $limit -p tblastn -i $fasta_file -d $database -o $out_file
        # NEW SYNTAX: tblastn -query <queryfile> -db <basename> -out <out_aln_file> -outfmt 0/7 (8 became 7) -evalue <e_value> -dust no (DNA) -seg no (AA) -num_threads <num_cores>
        #
        blast_bin = self.tBLASTn
        blast_cmd = [blast_bin]

        # check for necessary files
        if not os.path.isfile(blast_bin):
            raise ValueError("no such file '"+blast_bin+"'")
        if not os.path.isfile(one_forward_reads_file_path):
            raise ValueError("no such file '"+one_forward_reads_file_path+"'")
        elif not os.path.getsize(one_forward_reads_file_path) > 0:
            raise ValueError("empty file '"+one_forward_reads_file_path+"'")
        if not os.path.isfile(many_forward_reads_file_path):
            raise ValueError("no such file '"+many_forward_reads_file_path+"'")
        elif not os.path.getsize(many_forward_reads_file_path):
            raise ValueError("empty file '"+many_forward_reads_file_path+"'")

        # set the output path
        timestamp = int((datetime.utcnow() - datetime.utcfromtimestamp(0)).total_seconds()*1000)
        output_dir = os.path.join(self.scratch,'output.'+str(timestamp))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_aln_file_path = os.path.join(output_dir, 'alnout.txt');
        output_filtered_fasta_file_path = os.path.join(output_dir, 'output_filtered.fna');

        # this is command for basic search mode
        blast_cmd.append('-query')
        blast_cmd.append(one_forward_reads_file_path)
        blast_cmd.append('-db')
        blast_cmd.append(many_forward_reads_file_path)
        blast_cmd.append('-out')
        blast_cmd.append(output_aln_file_path)
        blast_cmd.append('-outfmt')
        blast_cmd.append('7')
        blast_cmd.append('-evalue')
        blast_cmd.append(str(params['e_value']))

        # options
        if 'maxaccepts' in params:
            if params['maxaccepts']:
                blast_cmd.append('-max_target_seqs')
                blast_cmd.append(str(params['maxaccepts']))

        # Run BLAST, capture output as it happens
        #
        self.log(console, 'RUNNING BLAST:')
        self.log(console, '    '+' '.join(blast_cmd))
#        report += "\n"+'running BLAST:'+"\n"
#        report += '    '+' '.join(blast_cmd)+"\n"

        p = subprocess.Popen(blast_cmd, \
                             cwd = self.scratch, \
                             stdout = subprocess.PIPE, \
                             stderr = subprocess.STDOUT, \
                             shell = False)

        while True:
            line = p.stdout.readline()
            if not line: break
            self.log(console, line.replace('\n', ''))

        p.stdout.close()
        p.wait()
        self.log(console, 'return code: ' + str(p.returncode))
        if p.returncode != 0:
            raise ValueError('Error running BLAST, return code: '+str(p.returncode) + 
                '\n\n'+ '\n'.join(console))


        # get query_len for filtering later
        #
        query_len = 0
        with open(one_forward_reads_file_path, 'r', 0) as query_file_handle:
            for line in query_file_handle:
                if line.startswith('>'):
                    continue
                query_len += len(re.sub(r" ","", line.rstrip())) 
        #query_len = query_len/1.0  # tBLASTn is prot-nuc

                
        # Parse the BLAST tabular output and store ids to filter many set to make filtered object to save back to KBase
        #
        self.log(console, 'PARSING BLAST ALIGNMENT OUTPUT')
        if not os.path.isfile(output_aln_file_path):
            raise ValueError("failed to create BLAST output: "+output_aln_file_path)
        elif not os.path.getsize(output_aln_file_path) > 0:
            raise ValueError("created empty file for BLAST output: "+output_aln_file_path)
        hit_seq_ids = dict()
        output_aln_file_handle = open (output_aln_file_path, "r", 0)
        output_aln_buf = output_aln_file_handle.readlines()
        output_aln_file_handle.close()
        hit_total = 0
        high_bitscore_line = dict()
        high_bitscore_score = dict()
        high_bitscore_ident = dict()
        high_bitscore_alnlen = dict()
        hit_order = []
        hit_buf = []
        header_done = False
        for line in output_aln_buf:
            if line.startswith('#'):
                if not header_done:
                    hit_buf.append(line)
                continue
            header_done = True
            #self.log(console,'HIT LINE: '+line)  # DEBUG
            hit_info = line.split("\t")
            hit_seq_id     = hit_info[1]
            hit_ident      = float(hit_info[2]) / 100.0
            hit_aln_len    = hit_info[3]
            hit_mismatches = hit_info[4]
            hit_gaps       = hit_info[5]
            hit_q_beg      = hit_info[6]
            hit_q_end      = hit_info[7]
            hit_t_beg      = hit_info[8]
            hit_t_end      = hit_info[9]
            hit_e_value    = hit_info[10]
            hit_bitscore   = hit_info[11]

            # BLAST SOMETIMES ADDS THIS TO IDs.  NO IDEA WHY, BUT GET RID OF IT!
            if hit_seq_id.startswith('gnl|'):
                hit_seq_id = hit_seq_id[4:]

            try:
                if float(hit_bitscore) > float(high_bitscore_score[hit_seq_id]):
                    high_bitscore_score[hit_seq_id] = hit_bitscore
                    high_bitscore_ident[hit_seq_id] = hit_ident
                    high_bitscore_alnlen[hit_seq_id] = hit_aln_len
                    high_bitscore_line[hit_seq_id] = line
            except:
                hit_order.append(hit_seq_id)
                high_bitscore_score[hit_seq_id] = hit_bitscore
                high_bitscore_ident[hit_seq_id] = hit_ident
                high_bitscore_alnlen[hit_seq_id] = hit_aln_len
                high_bitscore_line[hit_seq_id] = line

        for hit_seq_id in hit_order:
            hit_buf.append(high_bitscore_line[hit_seq_id])

            #self.log(console,"HIT_SEQ_ID: '"+hit_seq_id+"'")
            if 'ident_thresh' in params and float(params['ident_thresh']) > float(high_bitscore_ident[hit_seq_id]):
                continue
            if 'bitscore' in params and float(params['bitscore']) > float(high_bitscore_score[hit_seq_id]):
                continue
            if 'overlap_fraction' in params and float(params['overlap_fraction']) > float(high_bitscore_alnlen[hit_seq_id])/float(query_len):
                continue
            
            hit_total += 1
            hit_seq_ids[hit_seq_id] = True
            self.log(console, "HIT: '"+hit_seq_id+"'")  # DEBUG
        

        self.log(console, 'EXTRACTING HITS FROM INPUT')
        self.log(console, 'MANY_TYPE_NAME: '+many_type_name)  # DEBUG


        # SingleEndLibrary input -> SingleEndLibrary output
        #
        if many_type_name == 'SingleEndLibrary':

            #  Note: don't use SeqIO.parse because loads everything into memory
            #
#            with open(many_forward_reads_file_path, 'r', -1) as many_forward_reads_file_handle, open(output_filtered_fasta_file_path, 'w', -1) as output_filtered_fasta_file_handle:
            output_filtered_fasta_file_handle = open(output_filtered_fasta_file_path, 'w', -1)
            if many_forward_reads_file_compression == 'gz':
                many_forward_reads_file_handle = gzip.open(many_forward_reads_file_path, 'r', -1)
            else:
                many_forward_reads_file_handle = open(many_forward_reads_file_path, 'r', -1)

            seq_total = 0;
            filtered_seq_total = 0
            last_seq_buf = []
            last_seq_id = None
            last_header = None
            pattern = re.compile('^\S*')
            for line in many_forward_reads_file_handle:
                if line.startswith('>'):
                    #self.log(console, 'LINE: '+line)  # DEBUG
                    seq_total += 1
                    seq_id = line[1:]  # removes '>'
                    seq_id = pattern.findall(seq_id)[0]

                    if last_seq_id != None:
                        #self.log(console, 'ID: '+last_seq_id)  # DEBUG
                        try:
                            in_filtered_set = hit_seq_ids[last_seq_id]
                            #self.log(console, 'FOUND HIT '+last_seq_id)  # DEBUG
                            filtered_seq_total += 1
                            output_filtered_fasta_file_handle.write(last_header)
                            output_filtered_fasta_file_handle.writelines(last_seq_buf)
                        except:
                            pass
                        
                    last_seq_buf = []
                    last_seq_id = seq_id
                    last_header = line
                else:
                    last_seq_buf.append(line)

            if last_seq_id != None:
                #self.log(console, 'ID: '+last_seq_id)  # DEBUG
                try:
                    in_filtered_set = hit_seq_ids[last_seq_id]
                    #self.log(console, 'FOUND HIT: '+last_seq_id)  # DEBUG
                    filtered_seq_total += 1
                    output_filtered_fasta_file_handle.write(last_header)
                    output_filtered_fasta_file_handle.writelines(last_seq_buf)
                except:
                    pass
                
            last_seq_buf = []
            last_seq_id = None
            last_header = None

            many_forward_reads_file_handle.close()
            output_filtered_fasta_file_handle.close()

            if filtered_seq_total != hit_total:
                self.log(console,'hits in BLAST alignment output '+str(hit_total)+' != '+str(filtered_seq_total)+' matched sequences in input file')
                raise ValueError('hits in BLAST alignment output '+str(hit_total)+' != '+str(filtered_seq_total)+' matched sequences in input file')


        # FeatureSet input -> FeatureSet output
        #
        elif many_type_name == 'FeatureSet':

            seq_total = len(input_many_featureSet['elements'].keys())

            output_featureSet = dict()
            if 'description' in input_many_featureSet and input_many_featureSet['description'] != None:
                output_featureSet['description'] = input_many_featureSet['description'] + " - tBLASTn_Search filtered"
            else:
                output_featureSet['description'] = "tBLASTn_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()
            if 'element_ordering' in input_many_featureSet and input_many_featureSet['element_ordering'] != None:
                for fId in input_many_featureSet['element_ordering']:
                    try:
                        in_filtered_set = hit_seq_ids[fId]
                        #self.log(console, 'FOUND HIT '+fId)  # DEBUG
                        output_featureSet['element_ordering'].append(fId)
                        output_featureSet['elements'][fId] = input_many_featureSet['elements'][fId]
                    except:
                        pass
            else:
                fId_list = input_many_featureSet['elements'].keys()
                self.log(console,"ADDING FEATURES TO FEATURESET")
                for fId in sorted(fId_list):
                    try:
                        #self.log(console,"checking '"+fId+"'")
                        in_filtered_set = hit_seq_ids[fId]
                        #self.log(console, 'FOUND HIT '+fId)  # DEBUG
                        output_featureSet['element_ordering'].append(fId)
                        output_featureSet['elements'][fId] = input_many_featureSet['elements'][fId]
                    except:
                        pass

        # Parse Genome hits into FeatureSet
        #
        elif many_type_name == 'Genome':
            seq_total = 0

            output_featureSet = dict()
            if 'scientific_name' in input_many_genome and input_many_genome['scientific_name'] != None:
                output_featureSet['description'] = input_many_genome['scientific_name'] + " - tBLASTn_Search filtered"
            else:
                output_featureSet['description'] = "tBLASTn_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()
            for feature in input_many_genome['features']:
                seq_total += 1
                try:
                    in_filtered_set = hit_seq_ids[feature['id']]
                    #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
                    output_featureSet['element_ordering'].append(feature['id'])
                    output_featureSet['elements'][feature['id']] = [input_many_ref]
                except:
                    pass

        # Parse GenomeSet hits into FeatureSet
        #
        elif many_type_name == 'GenomeSet':
            seq_total = 0

            output_featureSet = dict()
            if 'description' in input_many_genomeSet and input_many_genomeSet['description'] != None:
                output_featureSet['description'] = input_many_genomeSet['description'] + " - tBLASTn_Search filtered"
            else:
                output_featureSet['description'] = "tBLASTn_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()

            for genome_name in input_many_genomeSet['elements'].keys():
                if 'ref' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['ref'] != None:
                    genomeRef = input_many_genomeSet['elements'][genome_name]['ref']
                    genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                    for feature in genome['features']:
                        seq_total += 1
                        try:
                            in_filtered_set = hit_seq_ids[feature['id']]
                            #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
                            output_featureSet['element_ordering'].append(feature['id'])
                            output_featureSet['elements'][feature['id']] = [genomeRef]
                        except:
                            pass

                elif 'data' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['data'] != None:
#                    genome = input_many_genomeSet['elements'][genome_name]['data']
#                    for feature in genome['features']:
#                        #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
#                        seq_total += 1
#                        try:
#                            in_filtered_set = hit_seq_ids[feature['id']]
#                            #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
#                            output_featureSet['element_ordering'].append(feature['id'])
                    raise ValueError ("FAILURE: unable to address genome object that is stored within 'data' field of genomeSet object")
#                            output_featureSet['elements'][feature['id']] = [genomeRef_is_inside_data_within_genomeSet_object_and_that_cant_be_addressed]
#                        except:
#                            pass


        # load the method provenance from the context object
        #
        self.log(console,"SETTING PROVENANCE")  # DEBUG
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects'] = []
        if 'input_one_name' in params and params['input_one_name'] != None:
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_one_name'])
        provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_many_name'])
        provenance[0]['service'] = 'kb_blast'
        provenance[0]['method'] = 'tBLASTn_Search'


        # Upload results
        #
        if len(invalid_msgs) == 0:
            self.log(console,"UPLOADING RESULTS")  # DEBUG

            if many_type_name == 'SingleEndLibrary':
                
                # input SingleEndLibrary -> upload SingleEndLibrary
                #
                self.upload_SingleEndLibrary_to_shock_and_ws (ctx,
                                                          console,  # DEBUG
                                                          params['workspace_name'],
                                                          params['output_filtered_name'],
                                                          output_filtered_fasta_file_path,
                                                          provenance,
                                                          sequencing_tech
                                                         )

            else:  # input FeatureSet, Genome, and GenomeSet -> upload FeatureSet output
                new_obj_info = ws.save_objects({
                            'workspace': params['workspace_name'],
                            'objects':[{
                                    'type': 'KBaseCollections.FeatureSet',
                                    'data': output_featureSet,
                                    'name': params['output_filtered_name'],
                                    'meta': {},
                                    'provenance': provenance
                                }]
                        })

        # build output report object
        #
        self.log(console,"BUILDING REPORT")  # DEBUG
        if len(invalid_msgs) == 0:
            report += 'sequences in many set: '+str(seq_total)+"\n"
            report += 'sequences in hit set:  '+str(hit_total)+"\n"
            report += "\n"
            for line in hit_buf:
                report += line
            reportObj = {
                'objects_created':[{'ref':params['workspace_name']+'/'+params['output_filtered_name'], 'description':'tBLASTn_Search hits'}],
                'text_message':report
                }
        else:
            report += "FAILURE\n\n"+"\n".join(invalid_msgs)+"\n"
            reportObj = {
                'objects_created':[],
                'text_message':report
                }

        reportName = 'blast_report_'+str(hex(uuid.getnode()))
        report_obj_info = ws.save_objects({
#                'id':info[6],
                'workspace':params['workspace_name'],
                'objects':[
                    {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance
                    }
                ]
            })[0]

        self.log(console,"BUILDING RETURN OBJECT")
#        returnVal = { 'output_report_name': reportName,
#                      'output_report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
#                      'output_filtered_ref': params['workspace_name']+'/'+params['output_filtered_name']
#                      }
        returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
        self.log(console,"tBLASTn_Search DONE")
        #END tBLASTn_Search

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method tBLASTn_Search return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]


    def tBLASTx_Search(self, ctx, params):
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN tBLASTx_Search
        console = []
        invalid_msgs = []
        self.log(console,'Running tBLASTx_Search with params=')
        self.log(console, "\n"+pformat(params))
        report = ''
#        report = 'Running tBLASTx_Search with params='
#        report += "\n"+pformat(params)


        #### do some basic checks
        #
        if 'workspace_name' not in params:
            raise ValueError('workspace_name parameter is required')
#        if 'input_one_name' not in params and 'input_one_sequence' not in params:
#            raise ValueError('input_one_sequence or input_one_name parameter is required')
        if 'input_one_name' not in params:
            raise ValueError('input_one_name parameter is required')
        if 'input_many_name' not in params:
            raise ValueError('input_many_name parameter is required')
        if 'output_filtered_name' not in params:
            raise ValueError('output_filtered_name parameter is required')


        # Write the input_one_sequence to a SingleEndLibrary object
        #
        if 'input_one_sequence' in params \
                and params['input_one_sequence'] != None \
                and params['input_one_sequence'] != "Optionally enter DNA sequence...":
            input_one_file_name = params['input_one_name']
            one_forward_reads_file_path = os.path.join(self.scratch,input_one_file_name)
            one_forward_reads_file_handle = open(one_forward_reads_file_path, 'w', 0)
            self.log(console, 'writing query reads file: '+str(one_forward_reads_file_path))

#            input_sequence_buf = params['input_one_sequence'].split("\n")
#            one_forward_reads_file_handle.write('>'+params['input_one_name']+"\n")
#            query_line_seen = False
#            for line in input_sequence_buf:
#                if not line.startswith('>'):
#                    one_forward_reads_file_handle.write(line+"\n")
#                else:
#                    if query_line_seen:
#                        break
#                    query_line_seen = True
#            one_forward_reads_file_handle.close();

            fastq_format = False
            input_sequence_buf = params['input_one_sequence']
            input_sequence_buf = input_sequence_buf.strip()
            if input_sequence_buf.startswith('@'):
                fastq_format = True
                #self.log(console,"INPUT_SEQ BEFORE: '''\n"+input_sequence_buf+"\n'''")  # DEBUG
            input_sequence_buf = re.sub ('&apos;', "'", input_sequence_buf)
            input_sequence_buf = re.sub ('&quot;', '"', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#39;',  "'", input_sequence_buf)
#        input_sequence_buf = re.sub ('&#34;',  '"', input_sequence_buf)
#        input_sequence_buf = re.sub ('&lt;;',  '<', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#60;',  '<', input_sequence_buf)
#        input_sequence_buf = re.sub ('&gt;',   '>', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#62;',  '>', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#36;',  '$', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#37;',  '%', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#47;',  '/', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#63;',  '?', input_sequence_buf)
##        input_sequence_buf = re.sub ('&#92;',  chr(92), input_sequence_buf)  # FIX LATER
#        input_sequence_buf = re.sub ('&#96;',  '`', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#124;', '|', input_sequence_buf)
#        input_sequence_buf = re.sub ('&amp;', '&', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#38;', '&', input_sequence_buf)
#        self.log(console,"INPUT_SEQ AFTER: '''\n"+input_sequence_buf+"\n'''")  # DEBUG

            DNA_pattern = re.compile("^[acgtuACGTU ]+$")
            space_pattern = re.compile("^[ \t]*$")
            split_input_sequence_buf = input_sequence_buf.split("\n")

            # no header rows, just sequence
            if not input_sequence_buf.startswith('>') and not input_sequence_buf.startswith('@'):
                one_forward_reads_file_handle.write('>'+params['input_one_name']+"\n")
                for line in split_input_sequence_buf:
                    if not space_pattern.match(line):
                        line = re.sub (" ","",line)
                        line = re.sub ("\t","",line)
                        if not DNA_pattern.match(line):
                            self.log(invalid_msgs,"BAD record:\n"+line+"\n")
                            continue
                        one_forward_reads_file_handle.write(line.lower()+"\n")
                one_forward_reads_file_handle.close()

            else:
                # format checks
                for i,line in enumerate(split_input_sequence_buf):
                    if line.startswith('>') or line.startswith('@'):
                        if not DNA_pattern.match(split_input_sequence_buf[i+1]):
                            if fastq_format:
                                bad_record = "\n".join([split_input_sequence_buf[i],
                                                        split_input_sequence_buf[i+1],
                                                        split_input_sequence_buf[i+2],
                                                        split_input_sequence_buf[i+3]])
                            else:
                                bad_record = "\n".join([split_input_sequence_buf[i],
                                                    split_input_sequence_buf[i+1]])
                            self.log(invalid_msgs,"BAD record:\n"+bad_record+"\n")
                        if fastq_format and line.startswith('@'):
                            format_ok = True
                            seq_len = len(split_input_sequence_buf[i+1])
                            if not seq_len > 0:
                                format_ok = False
                            if not split_input_sequence_buf[i+2].startswith('+'):
                                format_ok = False
                            if not seq_len == len(split_input_sequence_buf[i+3]):
                                format_ok = False
                            if not format_ok:
                                bad_record = "\n".join([split_input_sequence_buf[i],
                                                    split_input_sequence_buf[i+1],
                                                    split_input_sequence_buf[i+2],
                                                    split_input_sequence_buf[i+3]])
                                self.log(invalid_msgs,"BAD record:\n"+bad_record+"\n")

                # write that sucker, removing spaces
                #
                #forward_reads_file_handle.write(input_sequence_buf)        input_sequence_buf = re.sub ('&quot;', '"', input_sequence_buf)
                for i,line in enumerate(split_input_sequence_buf):
                    if line.startswith('>'):
                        record_buf = []
                        record_buf.append(line)
                        for j in range(i+1,len(split_input_sequence_buf)):
                            if split_input_sequence_buf[j].startswith('>'):
                                break
                            seq_line = re.sub (" ","",split_input_sequence_buf[j])
                            seq_line = re.sub ("\t","",seq_line)
                            seq_line = seq_line.lower()
                            record_buf.append(seq_line)
                        record = "\n".join(record_buf)+"\n"
                        one_forward_reads_file_handle.write(record)
                        break  # only want first record
                    elif line.startswith('@'):
                        seq_line = re.sub (" ","",split_input_sequence_buf[i+1])
                        seq_line = re.sub ("\t","",seq_line)
                        seq_line = seq_line.lower()
                        qual_line = re.sub (" ","",split_input_sequence_buf[i+3])
                        qual_line = re.sub ("\t","",qual_line)
                        record = "\n".join([line, seq_line, split_input_sequence_buf[i+2], qual_line])+"\n"
                        one_forward_reads_file_handle.write(record)
                        break  # only want first record

                one_forward_reads_file_handle.close()


            # load the method provenance from the context object
            #
            self.log(console,"SETTING PROVENANCE")  # DEBUG
            provenance = [{}]
            if 'provenance' in ctx:
                provenance = ctx['provenance']
            # add additional info to provenance here, in this case the input data object reference
                provenance[0]['input_ws_objects'] = []
                provenance[0]['service'] = 'kb_blast'
                provenance[0]['method'] = 'tBLASTx_Search'

                
                # Upload results
                #
                self.log(console,"UPLOADING QUERY OBJECT")  # DEBUG

                sequencing_tech = 'N/A'
                self.upload_SingleEndLibrary_to_shock_and_ws (ctx,
                                                      console,  # DEBUG
                                                      params['workspace_name'],
                                                      params['input_one_name'],
                                                      one_forward_reads_file_path,
                                                      provenance,
                                                      sequencing_tech
                                                      )

            self.log(console, 'done')

        #### Get the input_one object
        ##
        try:
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_one_name']}])
            data = objects[0]['data']
            info = objects[0]['info']
            # Object Info Contents
            # absolute ref = info[6] + '/' + info[0] + '/' + info[4]
            # 0 - obj_id objid
            # 1 - obj_name name
            # 2 - type_string type
            # 3 - timestamp save_date
            # 4 - int version
            # 5 - username saved_by
            # 6 - ws_id wsid
            # 7 - ws_name workspace
            # 8 - string chsum
            # 9 - int size 
            # 10 - usermeta meta
            one_type_name = info[2].split('.')[1].split('-')[0]
        except Exception as e:
            raise ValueError('Unable to fetch input_one_name object from workspace: ' + str(e))
        #to get the full stack trace: traceback.format_exc()

        if 'input_one_sequence' in params \
                and params['input_one_sequence'] != None \
                and params['input_one_sequence'] != "Optionally enter DNA sequence..." \
                and one_type_name != 'SingleEndLibrary':

            self.log(invalid_msgs,"ERROR: Mismatched input type: input_one_name should be SingleEndLibrary instead of: "+one_type_name)

        # Handle overloading (input_one can be Feature, SingleEndLibrary, or FeatureSet)
        #
        if one_type_name == 'SingleEndLibrary':
            try:
                if 'lib' in data:
                    one_forward_reads = data['lib']['file']
                elif 'handle' in data:
                    one_forward_reads = data['handle']
                else:
                    self.log(console,"bad structure for 'one_forward_reads'")
                    raise ValueError("bad structure for 'one_forward_reads'")

                ### NOTE: this section is what could be replaced by the transform services
                one_forward_reads_file_path = os.path.join(self.scratch,one_forward_reads['file_name'])
                one_forward_reads_file_handle = open(one_forward_reads_file_path, 'w', 0)
                self.log(console, 'downloading reads file: '+str(one_forward_reads_file_path))
                headers = {'Authorization': 'OAuth '+ctx['token']}
                r = requests.get(one_forward_reads['url']+'/node/'+one_forward_reads['id']+'?download', stream=True, headers=headers)
                for chunk in r.iter_content(1024):
                    one_forward_reads_file_handle.write(chunk)
                one_forward_reads_file_handle.close();
                self.log(console, 'done')
                ### END NOTE


                # remove carriage returns
                new_file_path = one_forward_reads_file_path+"-CRfree"
                new_file_handle = open(new_file_path, 'w', 0)
                one_forward_reads_file_handle = open(one_forward_reads_file_path, 'r', 0)
                for line in one_forward_reads_file_handle:
                    line = re.sub("\r","",line)
                    new_file_handle.write(line)
                one_forward_reads_file_handle.close();
                new_file_handle.close()
                one_forward_reads_file_path = new_file_path


                # convert FASTQ to FASTA (if necessary)
                new_file_path = one_forward_reads_file_path+".fna"
                new_file_handle = open(new_file_path, 'w', 0)
                one_forward_reads_file_handle = open(one_forward_reads_file_path, 'r', 0)
                header = None
                last_header = None
                last_seq_buf = None
                last_line_was_header = False
                was_fastq = False
                for line in one_forward_reads_file_handle:
                    if line.startswith('>'):
                        break
                    elif line.startswith('@'):
                        was_fastq = True
                        header = line[1:]
                        if last_header != None:
                            new_file_handle.write('>'+last_header)
                            new_file_handle.write(last_seq_buf)
                        last_seq_buf = None
                        last_header = header
                        last_line_was_header = True
                    elif last_line_was_header:
                        last_seq_buf = line
                        last_line_was_header = False
                    else:
                        continue
                if last_header != None:
                    new_file_handle.write('>'+last_header)
                    new_file_handle.write(last_seq_buf)

                new_file_handle.close()
                one_forward_reads_file_handle.close()
                if was_fastq:
                    one_forward_reads_file_path = new_file_path

            except Exception as e:
                print(traceback.format_exc())
                raise ValueError('Unable to download single-end read library files: ' + str(e))

        elif one_type_name == 'FeatureSet':
            # retrieve sequences for features
            input_one_featureSet = data
            
            genome2Features = {}
            features = input_one_featureSet['elements']

            if len(features.keys()) == 0:
                self.log(console,"No features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                self.log(invalid_msgs,"No features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
            if len(features.keys()) > 1:
                self.log(console,"Too many features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                self.log(invalid_msgs,"Too many features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))

            for fId in features.keys():
                genomeRef = features[fId][0]
                if genomeRef not in genome2Features:
                    genome2Features[genomeRef] = []
                genome2Features[genomeRef].append(fId)

            # export features to FASTA file
            one_forward_reads_file_path = os.path.join(self.scratch, params['input_one_name']+".fasta")
            self.log(console, 'writing fasta file: '+one_forward_reads_file_path)
            records = []
            for genomeRef in genome2Features:
                genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                these_genomeFeatureIds = genome2Features[genomeRef]
                for feature in genome['features']:
                    if feature['id'] in these_genomeFeatureIds:
                        # tBLASTx is nuc-nuc (translated)
                        if feature['type'] != 'CDS':
                            self.log(console,params['input_one_name']+" feature type must be CDS")
                            self.log(invalid_msgs,params['input_one_name']+" feature type must be CDS")
                        #elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                        #    self.log(console,"bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                        #    raise ValueError ("bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                        else:
                            record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genomeRef+"."+feature['id'])
                            #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genomeRef+"."+feature['id'])
                            records.append(record)
                            SeqIO.write(records, one_forward_reads_file_path, "fasta")
                            break  # just want one record

        elif one_type_name == 'Feature':
            # export feature to FASTA file
            feature = data
            one_forward_reads_file_path = os.path.join(self.scratch, params['input_one_name']+".fasta")
            self.log(console, 'writing fasta file: '+one_forward_reads_file_path)
            # tBLASTx is nuc-nuc (translated)
            if feature['type'] != 'CDS':
                self.log(console,params['input_one_name']+" feature type must be CDS")
                self.log(invalid_msgs,params['input_one_name']+" feature type must be CDS")
            #elif 'protein_translation' not in feature or feature['protein_translation'] == None:
            #    self.log(console,"bad CDS Feature "+params['input_one_name']+": no protein_translation found")
            #    raise ValueError ("bad CDS Feature "+params['input_one_name']+": no protein_translation found")
            else:
                record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genomeRef+"."+feature['id'])
                #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genomeRef+"."+feature['id'])
                SeqIO.write([record], one_forward_reads_file_path, "fasta")

        else:
            raise ValueError('Cannot yet handle input_one type of: '+type_name)            

        #### Get the input_many object
        ##
        many_forward_reads_file_compression = None
        sequencing_tech = 'N/A'
        try:
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_many_name']}])
            data = objects[0]['data']
            info = objects[0]['info']
            input_many_ref = str(info[6])+'/'+str(info[0])+'/'+str(info[4])
            many_type_name = info[2].split('.')[1].split('-')[0]

            if many_type_name == 'SingleEndLibrary':
                many_type_namespace = info[2].split('.')[0]
                if many_type_namespace == 'KBaseAssembly':
                    file_name = data['handle']['file_name']
                elif many_type_namespace == 'KBaseFile':
                    file_name = data['lib']['file']['file_name']
                else:
                    raise ValueError('bad data type namespace: '+many_type_namespace)
                #self.log(console, 'INPUT_MANY_FILENAME: '+file_name)  # DEBUG
                if file_name[-3:] == ".gz":
                    many_forward_reads_file_compression = 'gz'
                if 'sequencing_tech' in data:
                    sequencing_tech = data['sequencing_tech']

        except Exception as e:
            raise ValueError('Unable to fetch input_many_name object from workspace: ' + str(e))
            #to get the full stack trace: traceback.format_exc()

        # Handle overloading (input_many can be SingleEndLibrary, FeatureSet, Genome, or GenomeSet)
        #
        if many_type_name == 'SingleEndLibrary':

            # DEBUG
            #for k in data:
            #    self.log(console,"SingleEndLibrary ["+k+"]: "+str(data[k]))

            try:
                if 'lib' in data:
                    many_forward_reads = data['lib']['file']
                elif 'handle' in data:
                    many_forward_reads = data['handle']
                else:
                    self.log(console,"bad structure for 'many_forward_reads'")
                    raise ValueError("bad structure for 'many_forward_reads'")
                #if 'lib2' in data:
                #    reverse_reads = data['lib2']['file']
                #elif 'handle_2' in data:
                #    reverse_reads = data['handle_2']
                #else:
                #    reverse_reads={}

                ### NOTE: this section is what could be replaced by the transform services
                many_forward_reads_file_path = os.path.join(self.scratch,many_forward_reads['file_name'])
                many_forward_reads_file_handle = open(many_forward_reads_file_path, 'w', 0)
                self.log(console, 'downloading reads file: '+str(many_forward_reads_file_path))
                headers = {'Authorization': 'OAuth '+ctx['token']}
                r = requests.get(many_forward_reads['url']+'/node/'+many_forward_reads['id']+'?download', stream=True, headers=headers)
                for chunk in r.iter_content(1024):
                    many_forward_reads_file_handle.write(chunk)
                many_forward_reads_file_handle.close();
                self.log(console, 'done')
                ### END NOTE


                # remove carriage returns
                new_file_path = many_forward_reads_file_path+"-CRfree"
                new_file_handle = open(new_file_path, 'w', 0)
                many_forward_reads_file_handle = open(many_forward_reads_file_path, 'r', 0)
                for line in many_forward_reads_file_handle:
                    line = re.sub("\r","",line)
                    new_file_handle.write(line)
                many_forward_reads_file_handle.close();
                new_file_handle.close()
                many_forward_reads_file_path = new_file_path


                # convert FASTQ to FASTA (if necessary)
                new_file_path = many_forward_reads_file_path+".fna"
                new_file_handle = open(new_file_path, 'w', 0)
                if many_forward_reads_file_compression == 'gz':
                    many_forward_reads_file_handle = gzip.open(many_forward_reads_file_path, 'r', 0)
                else:
                    many_forward_reads_file_handle = open(many_forward_reads_file_path, 'r', 0)
                header = None
                last_header = None
                last_seq_buf = None
                last_line_was_header = False
                was_fastq = False
                for line in many_forward_reads_file_handle:
                    if line.startswith('>'):
                        break
                    elif line.startswith('@'):
                        was_fastq = True
                        header = line[1:]
                        if last_header != None:
                            new_file_handle.write('>'+last_header)
                            new_file_handle.write(last_seq_buf)
                        last_seq_buf = None
                        last_header = header
                        last_line_was_header = True
                    elif last_line_was_header:
                        last_seq_buf = line
                        last_line_was_header = False
                    else:
                        continue
                if last_header != None:
                    new_file_handle.write('>'+last_header)
                    new_file_handle.write(last_seq_buf)

                new_file_handle.close()
                many_forward_reads_file_handle.close()
                if was_fastq:
                    many_forward_reads_file_path = new_file_path

            except Exception as e:
                print(traceback.format_exc())
                raise ValueError('Unable to download single-end read library files: ' + str(e))

        # FeatureSet
        #
        elif many_type_name == 'FeatureSet':
            # retrieve sequences for features
            input_many_featureSet = data

            genome2Features = {}
            features = input_many_featureSet['elements']
            for fId in features.keys():
                genomeRef = features[fId][0]
                if genomeRef not in genome2Features:
                    genome2Features[genomeRef] = []
                genome2Features[genomeRef].append(fId)

            # export features to FASTA file
            many_forward_reads_file_path = os.path.join(self.scratch, params['input_many_name']+".fasta")
            self.log(console, 'writing fasta file: '+many_forward_reads_file_path)
            records = []
            feature_written = dict()
            for genomeRef in genome2Features:
                genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                these_genomeFeatureIds = genome2Features[genomeRef]
                for feature in genome['features']:
                    if feature['id'] in these_genomeFeatureIds:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG

                            # tBLASTx is nuc-nuc (translated)
                            if feature['type'] != 'CDS':
                                self.log(console,params['input_many_name']+" features must all be CDS type")
                                continue
                            #elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                            #    self.log(console,"bad CDS feature "+feature['id'])
                            #    raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                                #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)
            SeqIO.write(records, many_forward_reads_file_path, "fasta")


        # Genome
        #
        elif many_type_name == 'Genome':
            input_many_genome = data
            many_forward_reads_file_dir = self.scratch
            many_forward_reads_file = params['input_many_name']+".fasta"

            many_forward_reads_file_path = self.KB_SDK_data2file_Genome2Fasta (
                genome_object = input_many_genome,
                file          = many_forward_reads_file,
                dir           = many_forward_reads_file_dir,
                console       = console,
                invalid_msgs  = invalid_msgs,
                residue_type  = 'nucleotide',
                feature_type  = 'CDS',
                record_id_pattern = '%%feature_id%%',
                record_desc_pattern = '[%%genome_id%%]',
                case='upper',
                linewrap=50)


        # GenomeSet
        #
        elif many_type_name == 'GenomeSet':
            input_many_genomeSet = data

            # export features to FASTA file
            many_forward_reads_file_path = os.path.join(self.scratch, params['input_many_name']+".fasta")
            self.log(console, 'writing fasta file: '+many_forward_reads_file_path)

            records = []
            feature_written = dict()
            for genome_name in input_many_genomeSet['elements'].keys():
                if 'ref' in input_many_genomeSet['elements'][genome_name] and \
                         input_many_genomeSet['elements'][genome_name]['ref'] != None:
                    genome = ws.get_objects([{'ref': input_many_genomeSet['elements'][genome_name]['ref']}])[0]['data']
                    for feature in genome['features']:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG

                            # tBLASTx is nuc-nuc (translated)
                            if feature['type'] != 'CDS':
                                #self.log(console,params['input_many_name']+" features must all be CDS type")
                                continue
                            #elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                            #    self.log(console,"bad CDS feature "+feature['id'])
                            #    raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                                #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)

                elif 'data' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['data'] != None:
                    genome = input_many_genomeSet['elements'][genome_name]['data']
                    for feature in genome['features']:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG

                            # tBLASTx is nuc-nuc (translated)
                            if feature['type'] != 'CDS':
                                #self.log(console,params['input_many_name']+" features must all be CDS type")
                                continue
                            #elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                            #    self.log(console,"bad CDS feature "+feature['id'])
                            #    raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                                #record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)

                else:
                    raise ValueError('genome '+genome_name+' missing')

            SeqIO.write(records, many_forward_reads_file_path, "fasta")
            
        # Missing proper input_many_type
        #
        else:
            raise ValueError('Cannot yet handle input_many type of: '+type_name)            

        #
        # no input validation because query and db are both nuc
        #


        # FORMAT DB
        #
        # OLD SYNTAX: formatdb -i $database -o T -p F -> $database.nsq or $database.00.nsq
        # NEW SYNTAX: makeblastdb -in $database -parse_seqids -dbtype prot/nucl -out <basename>
        makeblastdb_cmd = [self.Make_BLAST_DB]

        # check for necessary files
        if not os.path.isfile(self.Make_BLAST_DB):
            raise ValueError("no such file '"+self.Make_BLAST_DB+"'")
        if not os.path.isfile(many_forward_reads_file_path):
            raise ValueError("no such file '"+many_forward_reads_file_path+"'")
        elif not os.path.getsize(many_forward_reads_file_path) > 0:
            raise ValueError("empty file '"+many_forward_reads_file_path+"'")

        makeblastdb_cmd.append('-in')
        makeblastdb_cmd.append(many_forward_reads_file_path)
        makeblastdb_cmd.append('-parse_seqids')
        makeblastdb_cmd.append('-dbtype')
        makeblastdb_cmd.append('nucl')
        makeblastdb_cmd.append('-out')
        makeblastdb_cmd.append(many_forward_reads_file_path)

        # Run Make_BLAST_DB, capture output as it happens
        #
        self.log(console, 'RUNNING Make_BLAST_DB:')
        self.log(console, '    '+' '.join(makeblastdb_cmd))
#        report += "\n"+'running Make_BLAST_DB:'+"\n"
#        report += '    '+' '.join(makeblastdb_cmd)+"\n"

        p = subprocess.Popen(makeblastdb_cmd, \
                             cwd = self.scratch, \
                             stdout = subprocess.PIPE, \
                             stderr = subprocess.STDOUT, \
                             shell = False)

        while True:
            line = p.stdout.readline()
            if not line: break
            self.log(console, line.replace('\n', ''))

        p.stdout.close()
        p.wait()
        self.log(console, 'return code: ' + str(p.returncode))
        if p.returncode != 0:
            raise ValueError('Error running makeblastdb, return code: '+str(p.returncode) + 
                '\n\n'+ '\n'.join(console))

        # Check for db output
        if not os.path.isfile(many_forward_reads_file_path+".nsq") and not os.path.isfile(many_forward_reads_file_path+".00.nsq"):
            raise ValueError("makeblastdb failed to create DB file '"+many_forward_reads_file_path+".nsq'")
        elif not os.path.getsize(many_forward_reads_file_path+".nsq") > 0 and not os.path.getsize(many_forward_reads_file_path+".00.nsq") > 0:
            raise ValueError("makeblastdb created empty DB file '"+many_forward_reads_file_path+".nsq'")


        ### Construct the BLAST command
        #
        # OLD SYNTAX: $blast -q $q -G $G -E $E -m $m -e $e_value -v $limit -b $limit -K $limit -p tblastx -i $fasta_file -d $database -o $out_file
        # NEW SYNTAX: tblastx -query <queryfile> -db <basename> -out <out_aln_file> -outfmt 0/7 (8 became 7) -evalue <e_value> -dust no (DNA) -seg no (AA) -num_threads <num_cores>
        #
        blast_bin = self.tBLASTx
        blast_cmd = [blast_bin]

        # check for necessary files
        if not os.path.isfile(blast_bin):
            raise ValueError("no such file '"+blast_bin+"'")
        if not os.path.isfile(one_forward_reads_file_path):
            raise ValueError("no such file '"+one_forward_reads_file_path+"'")
        elif not os.path.getsize(one_forward_reads_file_path) > 0:
            raise ValueError("empty file '"+one_forward_reads_file_path+"'")
        if not os.path.isfile(many_forward_reads_file_path):
            raise ValueError("no such file '"+many_forward_reads_file_path+"'")
        elif not os.path.getsize(many_forward_reads_file_path):
            raise ValueError("empty file '"+many_forward_reads_file_path+"'")

        # set the output path
        timestamp = int((datetime.utcnow() - datetime.utcfromtimestamp(0)).total_seconds()*1000)
        output_dir = os.path.join(self.scratch,'output.'+str(timestamp))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_aln_file_path = os.path.join(output_dir, 'alnout.txt');
        output_filtered_fasta_file_path = os.path.join(output_dir, 'output_filtered.fna');

        # this is command for basic search mode
        blast_cmd.append('-query')
        blast_cmd.append(one_forward_reads_file_path)
        blast_cmd.append('-db')
        blast_cmd.append(many_forward_reads_file_path)
        blast_cmd.append('-out')
        blast_cmd.append(output_aln_file_path)
        blast_cmd.append('-outfmt')
        blast_cmd.append('7')
        blast_cmd.append('-evalue')
        blast_cmd.append(str(params['e_value']))

        # options
        if 'maxaccepts' in params:
            if params['maxaccepts']:
                blast_cmd.append('-max_target_seqs')
                blast_cmd.append(str(params['maxaccepts']))

        # Run BLAST, capture output as it happens
        #
        self.log(console, 'RUNNING BLAST:')
        self.log(console, '    '+' '.join(blast_cmd))
#        report += "\n"+'running BLAST:'+"\n"
#        report += '    '+' '.join(blast_cmd)+"\n"

        p = subprocess.Popen(blast_cmd, \
                             cwd = self.scratch, \
                             stdout = subprocess.PIPE, \
                             stderr = subprocess.STDOUT, \
                             shell = False)

        while True:
            line = p.stdout.readline()
            if not line: break
            self.log(console, line.replace('\n', ''))

        p.stdout.close()
        p.wait()
        self.log(console, 'return code: ' + str(p.returncode))
        if p.returncode != 0:
            raise ValueError('Error running BLAST, return code: '+str(p.returncode) + 
                '\n\n'+ '\n'.join(console))


        # get query_len for filtering later
        #
        query_len = 0
        with open(one_forward_reads_file_path, 'r', 0) as query_file_handle:
            for line in query_file_handle:
                if line.startswith('>'):
                    continue
                query_len += len(re.sub(r" ","", line.rstrip())) 
        query_len = query_len/3.0  # tBLASTx is nuc-nuc (translated) and reports alnlen in protein length

                
        # Parse the BLAST tabular output and store ids to filter many set to make filtered object to save back to KBase
        #
        self.log(console, 'PARSING BLAST ALIGNMENT OUTPUT')
        if not os.path.isfile(output_aln_file_path):
            raise ValueError("failed to create BLAST output: "+output_aln_file_path)
        elif not os.path.getsize(output_aln_file_path) > 0:
            raise ValueError("created empty file for BLAST output: "+output_aln_file_path)
        hit_seq_ids = dict()
        output_aln_file_handle = open (output_aln_file_path, "r", 0)
        output_aln_buf = output_aln_file_handle.readlines()
        output_aln_file_handle.close()
        hit_total = 0
        high_bitscore_line = dict()
        high_bitscore_score = dict()
        high_bitscore_ident = dict()
        high_bitscore_alnlen = dict()
        hit_order = []
        hit_buf = []
        header_done = False
        for line in output_aln_buf:
            if line.startswith('#'):
                if not header_done:
                    hit_buf.append(line)
                continue
            header_done = True
            #self.log(console,'HIT LINE: '+line)  # DEBUG
            hit_info = line.split("\t")
            hit_seq_id     = hit_info[1]
            hit_ident      = float(hit_info[2]) / 100.0
            hit_aln_len    = hit_info[3]
            hit_mismatches = hit_info[4]
            hit_gaps       = hit_info[5]
            hit_q_beg      = hit_info[6]
            hit_q_end      = hit_info[7]
            hit_t_beg      = hit_info[8]
            hit_t_end      = hit_info[9]
            hit_e_value    = hit_info[10]
            hit_bitscore   = hit_info[11]

            # BLAST SOMETIMES ADDS THIS TO IDs.  NO IDEA WHY, BUT GET RID OF IT!
            if hit_seq_id.startswith('gnl|'):
                hit_seq_id = hit_seq_id[4:]

            try:
                if float(hit_bitscore) > float(high_bitscore_score[hit_seq_id]):
                    self.log(console,"OVERRIDE ID: "+hit_seq_id)  # DEBUG
                    self.log(console,line)  # DEBUG
                    high_bitscore_score[hit_seq_id] = hit_bitscore
                    high_bitscore_ident[hit_seq_id] = hit_ident
                    high_bitscore_alnlen[hit_seq_id] = hit_aln_len
                    high_bitscore_line[hit_seq_id] = line
            except:
                self.log(console,"NEW ID: "+hit_seq_id)  # DEBUG
                self.log(console,line)  # DEBUG
                hit_order.append(hit_seq_id)
                high_bitscore_score[hit_seq_id] = hit_bitscore
                high_bitscore_ident[hit_seq_id] = hit_ident
                high_bitscore_alnlen[hit_seq_id] = hit_aln_len
                high_bitscore_line[hit_seq_id] = line

        for hit_seq_id in hit_order:
            hit_buf.append(high_bitscore_line[hit_seq_id])

            #self.log(console,"HIT_SEQ_ID: '"+hit_seq_id+"'")
            if 'ident_thresh' in params and float(params['ident_thresh']) > float(high_bitscore_ident[hit_seq_id]):
                continue
            if 'bitscore' in params and float(params['bitscore']) > float(high_bitscore_score[hit_seq_id]):
                continue
            if 'overlap_fraction' in params and float(params['overlap_fraction']) > float(high_bitscore_alnlen[hit_seq_id])/float(query_len):
                continue
            
            hit_total += 1
            hit_seq_ids[hit_seq_id] = True
            self.log(console, "HIT: '"+hit_seq_id+"'")  # DEBUG
        

        self.log(console, 'EXTRACTING HITS FROM INPUT')
        self.log(console, 'MANY_TYPE_NAME: '+many_type_name)  # DEBUG


        # SingleEndLibrary input -> SingleEndLibrary output
        #
        if many_type_name == 'SingleEndLibrary':

            #  Note: don't use SeqIO.parse because loads everything into memory
            #
#            with open(many_forward_reads_file_path, 'r', -1) as many_forward_reads_file_handle, open(output_filtered_fasta_file_path, 'w', -1) as output_filtered_fasta_file_handle:
            output_filtered_fasta_file_handle = open(output_filtered_fasta_file_path, 'w', -1)
            if many_forward_reads_file_compression == 'gz':
                many_forward_reads_file_handle = gzip.open(many_forward_reads_file_path, 'r', -1)
            else:
                many_forward_reads_file_handle = open(many_forward_reads_file_path, 'r', -1)

            seq_total = 0;
            filtered_seq_total = 0
            last_seq_buf = []
            last_seq_id = None
            last_header = None
            pattern = re.compile('^\S*')
            for line in many_forward_reads_file_handle:
                if line.startswith('>'):
                    #self.log(console, 'LINE: '+line)  # DEBUG
                    seq_total += 1
                    seq_id = line[1:]  # removes '>'
                    seq_id = pattern.findall(seq_id)[0]

                    if last_seq_id != None:
                        #self.log(console, 'ID: '+last_seq_id)  # DEBUG
                        try:
                            in_filtered_set = hit_seq_ids[last_seq_id]
                            #self.log(console, 'FOUND HIT '+last_seq_id)  # DEBUG
                            filtered_seq_total += 1
                            output_filtered_fasta_file_handle.write(last_header)
                            output_filtered_fasta_file_handle.writelines(last_seq_buf)
                        except:
                            pass
                        
                    last_seq_buf = []
                    last_seq_id = seq_id
                    last_header = line
                else:
                    last_seq_buf.append(line)

            if last_seq_id != None:
                #self.log(console, 'ID: '+last_seq_id)  # DEBUG
                try:
                    in_filtered_set = hit_seq_ids[last_seq_id]
                    #self.log(console, 'FOUND HIT: '+last_seq_id)  # DEBUG
                    filtered_seq_total += 1
                    output_filtered_fasta_file_handle.write(last_header)
                    output_filtered_fasta_file_handle.writelines(last_seq_buf)
                except:
                    pass
                
            last_seq_buf = []
            last_seq_id = None
            last_header = None

            many_forward_reads_file_handle.close()
            output_filtered_fasta_file_handle.close()

            if filtered_seq_total != hit_total:
                self.log(console,'hits in BLAST alignment output '+str(hit_total)+' != '+str(filtered_seq_total)+' matched sequences in input file')
                raise ValueError('hits in BLAST alignment output '+str(hit_total)+' != '+str(filtered_seq_total)+' matched sequences in input file')


        # FeatureSet input -> FeatureSet output
        #
        elif many_type_name == 'FeatureSet':

            seq_total = len(input_many_featureSet['elements'].keys())

            output_featureSet = dict()
            if 'description' in input_many_featureSet and input_many_featureSet['description'] != None:
                output_featureSet['description'] = input_many_featureSet['description'] + " - tBLASTx_Search filtered"
            else:
                output_featureSet['description'] = "tBLASTx_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()
            if 'element_ordering' in input_many_featureSet and input_many_featureSet['element_ordering'] != None:
                for fId in input_many_featureSet['element_ordering']:
                    try:
                        in_filtered_set = hit_seq_ids[fId]
                        #self.log(console, 'FOUND HIT '+fId)  # DEBUG
                        output_featureSet['element_ordering'].append(fId)
                        output_featureSet['elements'][fId] = input_many_featureSet['elements'][fId]
                    except:
                        pass
            else:
                fId_list = input_many_featureSet['elements'].keys()
                self.log(console,"ADDING FEATURES TO FEATURESET")
                for fId in sorted(fId_list):
                    try:
                        #self.log(console,"checking '"+fId+"'")
                        in_filtered_set = hit_seq_ids[fId]
                        #self.log(console, 'FOUND HIT '+fId)  # DEBUG
                        output_featureSet['element_ordering'].append(fId)
                        output_featureSet['elements'][fId] = input_many_featureSet['elements'][fId]
                    except:
                        pass

        # Parse Genome hits into FeatureSet
        #
        elif many_type_name == 'Genome':
            seq_total = 0

            output_featureSet = dict()
            if 'scientific_name' in input_many_genome and input_many_genome['scientific_name'] != None:
                output_featureSet['description'] = input_many_genome['scientific_name'] + " - tBLASTx_Search filtered"
            else:
                output_featureSet['description'] = "tBLASTx_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()
            for feature in input_many_genome['features']:
                seq_total += 1
                try:
                    in_filtered_set = hit_seq_ids[feature['id']]
                    #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
                    output_featureSet['element_ordering'].append(feature['id'])
                    output_featureSet['elements'][feature['id']] = [input_many_ref]
                except:
                    pass

        # Parse GenomeSet hits into FeatureSet
        #
        elif many_type_name == 'GenomeSet':
            seq_total = 0

            output_featureSet = dict()
            if 'description' in input_many_genomeSet and input_many_genomeSet['description'] != None:
                output_featureSet['description'] = input_many_genomeSet['description'] + " - tBLASTx_Search filtered"
            else:
                output_featureSet['description'] = "tBLASTx_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()

            for genome_name in input_many_genomeSet['elements'].keys():
                if 'ref' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['ref'] != None:
                    genomeRef = input_many_genomeSet['elements'][genome_name]['ref']
                    genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                    for feature in genome['features']:
                        seq_total += 1
                        try:
                            in_filtered_set = hit_seq_ids[feature['id']]
                            #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
                            output_featureSet['element_ordering'].append(feature['id'])
                            output_featureSet['elements'][feature['id']] = [genomeRef]
                        except:
                            pass

                elif 'data' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['data'] != None:
#                    genome = input_many_genomeSet['elements'][genome_name]['data']
#                    for feature in genome['features']:
#                        #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
#                        seq_total += 1
#                        try:
#                            in_filtered_set = hit_seq_ids[feature['id']]
#                            #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
#                            output_featureSet['element_ordering'].append(feature['id'])
                    raise ValueError ("FAILURE: unable to address genome object that is stored within 'data' field of genomeSet object")
#                            output_featureSet['elements'][feature['id']] = [genomeRef_is_inside_data_within_genomeSet_object_and_that_cant_be_addressed]
#                        except:
#                            pass


        # load the method provenance from the context object
        #
        self.log(console,"SETTING PROVENANCE")  # DEBUG
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects'] = []
        if 'input_one_name' in params and params['input_one_name'] != None:
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_one_name'])
        provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_many_name'])
        provenance[0]['service'] = 'kb_blast'
        provenance[0]['method'] = 'tBLASTx_Search'


        # Upload results
        #
        if len(invalid_msgs) == 0:
            self.log(console,"UPLOADING RESULTS")  # DEBUG

            if many_type_name == 'SingleEndLibrary':
            
                # input SingleEndLibrary -> upload SingleEndLibrary
                #
                self.upload_SingleEndLibrary_to_shock_and_ws (ctx,
                                                          console,  # DEBUG
                                                          params['workspace_name'],
                                                          params['output_filtered_name'],
                                                          output_filtered_fasta_file_path,
                                                          provenance,
                                                          sequencing_tech
                                                         )

            else:  # input FeatureSet, Genome, and GenomeSet -> upload FeatureSet output
                new_obj_info = ws.save_objects({
                            'workspace': params['workspace_name'],
                            'objects':[{
                                    'type': 'KBaseCollections.FeatureSet',
                                    'data': output_featureSet,
                                    'name': params['output_filtered_name'],
                                    'meta': {},
                                    'provenance': provenance
                                }]
                        })

        # build output report object
        #
        self.log(console,"BUILDING REPORT")  # DEBUG
        if len(invalid_msgs) == 0:
            report += 'sequences in many set: '+str(seq_total)+"\n"
            report += 'sequences in hit set:  '+str(hit_total)+"\n"
            report += "\n"
            for line in hit_buf:
                report += line
            reportObj = {
                'objects_created':[{'ref':params['workspace_name']+'/'+params['output_filtered_name'], 'description':'tBLASTx_Search hits'}],
                'text_message':report
                }
        else:
            report += "FAILURE\n\n"+"\n".join(invalid_msgs)+"\n"
            reportObj = {
                'objects_created':[],
                'text_message':report
                }

        reportName = 'blast_report_'+str(hex(uuid.getnode()))
        report_obj_info = ws.save_objects({
#                'id':info[6],
                'workspace':params['workspace_name'],
                'objects':[
                    {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance
                    }
                ]
            })[0]

        self.log(console,"BUILDING RETURN OBJECT")
#        returnVal = { 'output_report_name': reportName,
#                      'output_report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
#                      'output_filtered_ref': params['workspace_name']+'/'+params['output_filtered_name']
#                      }
        returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
        self.log(console,"tBLASTx_Search DONE")
        #END tBLASTx_Search

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method tBLASTx_Search return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]

    def psiBLAST_msa_start_Search(self, ctx, params):
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN psiBLAST_msa_start_Search
        console = []
        invalid_msgs = []
        self.log(console,'Running psiBLAST_msa_start_Search with params=')
        self.log(console, "\n"+pformat(params))
        report = ''
#        report = 'Running psiBLAST_msa_start_Search with params='
#        report += "\n"+pformat(params)
        protein_sequence_found_in_one_input = False
        protein_sequence_found_in_MSA_input = False
        protein_sequence_found_in_many_input = False


        #### do some basic checks
        #
        if 'workspace_name' not in params:
            raise ValueError('workspace_name parameter is required')
        if 'input_one_name' not in params:
            raise ValueError('input_one_name parameter is required')
        if 'input_msa_name' not in params:
            raise ValueError('input_msa_name parameter is required')
        if 'input_many_name' not in params:
            raise ValueError('input_many_name parameter is required')
        if 'output_filtered_name' not in params:
            raise ValueError('output_filtered_name parameter is required')


        #### Get the input_one object
        ##
        input_one_id = None
        if 'input_one_name' in params and params['input_one_name'] != None:
            try:
                ws = workspaceService(self.workspaceURL, token=ctx['token'])
                objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_one_name']}])
                data = objects[0]['data']
                info = objects[0]['info']
                # Object Info Contents
                # absolute ref = info[6] + '/' + info[0] + '/' + info[4]
                # 0 - obj_id objid
                # 1 - obj_name name
                # 2 - type_string type
                # 3 - timestamp save_date
                # 4 - int version
                # 5 - username saved_by
                # 6 - ws_id wsid
                # 7 - ws_name workspace
                # 8 - string chsum
                # 9 - int size 
                # 10 - usermeta meta
                one_type_name = info[2].split('.')[1].split('-')[0]
            except Exception as e:
                raise ValueError('Unable to fetch input_one_name object from workspace: ' + str(e))
                #to get the full stack trace: traceback.format_exc()


            # Handle overloading (input_one can be Feature, or FeatureSet)
            #
            if one_type_name == 'FeatureSet':
                # retrieve sequences for features
                input_one_featureSet = data
            
                genome2Features = {}
                features = input_one_featureSet['elements']

                if len(features.keys()) == 0:
                    self.log(console,"No features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                    self.log(invalid_msgs,"No features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                if len(features.keys()) > 1:
                    self.log(console,"Too many features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))
                    self.log(invalid_msgs,"Too many features in "+params['input_one_name']+" feature set.  Should one have 1 instead of "+len(features.keys()))

                for fId in features.keys():
                    input_one_feature_id = fId
                    genomeRef = features[fId][0]
                    if genomeRef not in genome2Features:
                        genome2Features[genomeRef] = []
                    genome2Features[genomeRef].append(fId)

                # export features to FASTA file
                one_forward_reads_file_path = os.path.join(self.scratch, params['input_one_name']+".fasta")
                self.log(console, 'writing fasta file: '+one_forward_reads_file_path)
                records = []
                for genomeRef in genome2Features:
                    genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                    these_genomeFeatureIds = genome2Features[genomeRef]
                    for feature in genome['features']:
                        if feature['id'] in these_genomeFeatureIds:
                            # psiBLAST is prot-prot
                            #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genomeRef+"."+feature['id'])
                            if feature['type'] != 'CDS':
                                self.log(console,params['input_one_name']+" feature type must be CDS")
                                self.log(invalid_msgs,params['input_one_name']+" feature type must be CDS")
                            elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                                self.log(console,"bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                                raise ValueError ("bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                            else:
                                protein_sequence_found_in_one_input = True
                                record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genomeRef+"."+feature['id'])
                                records.append(record)
                                SeqIO.write(records, one_forward_reads_file_path, "fasta")
                                break  # only want first record

            elif one_type_name == 'Feature':
                # export feature to FASTA file
                feature = data
                input_one_feature_id = feature['id']
                one_forward_reads_file_path = os.path.join(self.scratch, params['input_one_name']+".fasta")
                self.log(console, 'writing fasta file: '+one_forward_reads_file_path)
                # psiBLAST is prot-prot
                #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description='['+feature['genome_id']+']'+' '+feature['function'])
                if feature['type'] != 'CDS':
                    self.log(console,params['input_one_name']+" feature type must be CDS")
                    self.log(invalid_msgs,params['input_one_name']+" feature type must be CDS")
                elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                    self.log(console,"bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                    raise ValueError ("bad CDS Feature "+params['input_one_name']+": no protein_translation found")
                else:
                    protein_sequence_found_in_one_input = True
                    record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description='['+feature['genome_id']+']'+' '+feature['function'])
                    SeqIO.write([record], one_forward_reads_file_path, "fasta")

            else:
                raise ValueError('Cannot yet handle input_one type of: '+type_name)            
        else:
            raise ValueError('Must define either input_one_sequence or input_one_name')


        #### Get the input_msa object
        ##
        if input_one_feature_id == None:
            self.log(invalid_msgs,"input_one_feature_id was not obtained from Query Object: "+params['input_one_name'])
        master_row_idx = 0
        try:
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_msa_name']}])
            data = objects[0]['data']
            info = objects[0]['info']
            input_msa_type = info[2].split('.')[1].split('-')[0]

        except Exception as e:
            raise ValueError('Unable to fetch input_msa_name object from workspace: ' + str(e))
            #to get the full stack trace: traceback.format_exc()

        if input_msa_type == 'MSA':
            MSA_in = data
            row_order = []
            default_row_labels = dict()
            if 'row_order' in MSA_in.keys():
                row_order = MSA_in['row_order']
            else:
                row_order = sorted(MSA_in['alignment'].keys())

            if 'default_row_labels' in MSA_in.keys():
                default_row_labels = MSA_in['default_row_labels']
            else:
                for row_id in row_order:
                    default_row_labels[row_id] = row_id

            # determine row index of query sequence
            for row_id in row_order:
                master_row_idx += 1
                if row_id == input_one_feature_id:
                    break
            if master_row_idx == 0:
                self.log(invalid_msgs,"Failed to find query id "+input_one_feature_id+" from Query Object "+params['input_one_name']+" within MSA: "+params['input_msa_name'])

            
            # export features to Clustal-esque file that PSI-BLAST likes
            input_MSA_file_path = os.path.join(self.scratch, params['input_msa_name']+".fasta")
            self.log(console, 'writing MSA file: '+input_MSA_file_path)
            records = []
            longest_row_id_len = 0
            for row_id in row_order:
                if len(row_id) > longest_row_id_len:
                    longest_row_id_len = len(row_id)
            for row_id in row_order:
                #self.log(console,"row_id: '"+row_id+"'")  # DEBUG
                #self.log(console,"alignment: '"+MSA_in['alignment'][row_id]+"'")  # DEBUG
                # using SeqIO makes multiline sequences.  We want Clustal-esque, but we'll not break them up and hope PSI-BLAST is happy
                #record = SeqRecord(Seq(MSA_in['alignment'][row_id]), id=row_id, description=default_row_labels[row_id])
                #records.append(record)
                #SeqIO.write(records, input_MSA_file_path, "fasta")
                padding = ''
                for i in range(0,longest_row_id_len-len(row_id)):
                    padding += ' '
                records.append(row_id + padding + "\t" +
                               MSA_in['alignment'][row_id]
                               )
            with open(input_MSA_file_path,'w',0) as input_MSA_file_handle:
                input_MSA_file_handle.write("\n".join(records)+"\n")


            # Determine whether nuc or protein sequences
            #
            NUC_MSA_pattern = re.compile("^[\.\-_ACGTUXNRYSWKMBDHVacgtuxnryswkmbdhv \t\n]+$")
            all_seqs_nuc = True
            for row_id in row_order:
                #self.log(console, row_id+": '"+MSA_in['alignment'][row_id]+"'")
                if NUC_MSA_pattern.match(MSA_in['alignment'][row_id]) == None:
                    all_seqs_nuc = False
                    break
                else:
                    protein_sequence_found_in_MSA_input = True

        # Missing proper input_type
        #
        else:
            raise ValueError('Cannot yet handle input_name type of: '+type_name)

        #### Get the input_many object
        ##
        try:
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_many_name']}])
            data = objects[0]['data']
            info = objects[0]['info']
            input_many_ref = str(info[6])+'/'+str(info[0])+'/'+str(info[4])
            many_type_name = info[2].split('.')[1].split('-')[0]

        except Exception as e:
            raise ValueError('Unable to fetch input_many_name object from workspace: ' + str(e))
            #to get the full stack trace: traceback.format_exc()

        # Handle overloading (input_many can be FeatureSet, Genome, or GenomeSet)
        #
        if many_type_name == 'FeatureSet':
            # retrieve sequences for features
            input_many_featureSet = data

            genome2Features = {}
            features = input_many_featureSet['elements']
            for fId in features.keys():
                genomeRef = features[fId][0]
                if genomeRef not in genome2Features:
                    genome2Features[genomeRef] = []
                genome2Features[genomeRef].append(fId)

            # export features to FASTA file
            many_forward_reads_file_path = os.path.join(self.scratch, params['input_many_name']+".fasta")
            self.log(console, 'writing fasta file: '+many_forward_reads_file_path)
            records = []
            feature_written = dict()
            for genomeRef in genome2Features:
                genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                these_genomeFeatureIds = genome2Features[genomeRef]
                for feature in genome['features']:
                    if feature['id'] in these_genomeFeatureIds:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG

                            # psiBLAST is prot-prot
                            if feature['type'] != 'CDS':
                                self.log(console,"skipping non-CDS feature "+feature['id'])
                                continue
                            elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                                self.log(console,"bad CDS feature "+feature['id'])
                                raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                protein_sequence_found_in_many_input = True
                                #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                                record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)
            SeqIO.write(records, many_forward_reads_file_path, "fasta")


        # Genome
        #
        elif many_type_name == 'Genome':
            input_many_genome = data
            many_forward_reads_file_dir = self.scratch
            many_forward_reads_file = params['input_many_name']+".fasta"

            many_forward_reads_file_path = self.KB_SDK_data2file_Genome2Fasta (
                genome_object = input_many_genome,
                file          = many_forward_reads_file,
                dir           = many_forward_reads_file_dir,
                console       = console,
                invalid_msgs  = invalid_msgs,
                residue_type  = 'protein',
                feature_type  = 'CDS',
                record_id_pattern = '%%feature_id%%',
                record_desc_pattern = '[%%genome_id%%]',
                case='upper',
                linewrap=50)

            protein_sequence_found_in_many_input = True  # FIX LATER


        # GenomeSet
        #
        elif many_type_name == 'GenomeSet':
            input_many_genomeSet = data

            # export features to FASTA file
            many_forward_reads_file_path = os.path.join(self.scratch, params['input_many_name']+".fasta")
            self.log(console, 'writing fasta file: '+many_forward_reads_file_path)

            records = []
            feature_written = dict()
            for genome_name in input_many_genomeSet['elements'].keys():
                if 'ref' in input_many_genomeSet['elements'][genome_name] and \
                         input_many_genomeSet['elements'][genome_name]['ref'] != None:
                    genome = ws.get_objects([{'ref': input_many_genomeSet['elements'][genome_name]['ref']}])[0]['data']
                    for feature in genome['features']:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
                            # psiBLAST is prot-prot
                            #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                            if feature['type'] != 'CDS':
                                #self.log(console,"skipping non-CDS feature "+feature['id'])  # too much chatter for a Genome
                                continue
                            elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                                self.log(console,"bad CDS feature "+feature['id'])
                                raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                protein_sequence_found_in_many_input = True
                                record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)

                elif 'data' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['data'] != None:
                    genome = input_many_genomeSet['elements'][genome_name]['data']
                    for feature in genome['features']:
                        try:
                            f_written = feature_written[feature['id']]
                        except:
                            feature_written[feature['id']] = True
                            #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
                            # psiBLAST is prot-prot
                            #record = SeqRecord(Seq(feature['dna_sequence']), id=feature['id'], description=genome['id'])
                            if feature['type'] != 'CDS':
                                continue
                            elif 'protein_translation' not in feature or feature['protein_translation'] == None:
                                self.log(console,"bad CDS feature "+feature['id'])
                                raise ValueError("bad CDS feature "+feature['id'])
                            else:
                                protein_sequence_found_in_many_input = True
                                record = SeqRecord(Seq(feature['protein_translation']), id=feature['id'], description=genome['id'])
                                records.append(record)

                else:
                    raise ValueError('genome '+genome_name+' missing')

            SeqIO.write(records, many_forward_reads_file_path, "fasta")
            
        # Missing proper input_many_type
        #
        else:
            raise ValueError('Cannot yet handle input_many type of: '+type_name)            


        # check for failed input file creation
        #
        if params['input_one_name'] != None:
            if not protein_sequence_found_in_one_input:
                self.log(invalid_msgs,"no protein sequences found in '"+params['input_one_name']+"'")
        if not protein_sequence_found_in_MSA_input:
            self.log(invalid_msgs,"no protein sequences found in '"+params['input_msa_name']+"'")
        if not protein_sequence_found_in_many_input:
            self.log(invalid_msgs,"no protein sequences found in '"+params['input_many_name']+"'")


        # input data failed validation.  Need to return
        #
        if len(invalid_msgs) > 0:

            # load the method provenance from the context object
            #
            self.log(console,"SETTING PROVENANCE")  # DEBUG
            provenance = [{}]
            if 'provenance' in ctx:
                provenance = ctx['provenance']
            # add additional info to provenance here, in this case the input data object reference
            provenance[0]['input_ws_objects'] = []
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_one_name'])
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_msa_name'])
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_many_name'])
            provenance[0]['service'] = 'kb_blast'
            provenance[0]['method'] = 'psiBLAST_msa_start_Search'


            # build output report object
            #
            self.log(console,"BUILDING REPORT")  # DEBUG
            report += "FAILURE:\n\n"+"\n".join(invalid_msgs)+"\n"
            reportObj = {
                'objects_created':[],
                'text_message':report
                }

            reportName = 'blast_report_'+str(hex(uuid.getnode()))
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            report_obj_info = ws.save_objects({
                    #'id':info[6],
                    'workspace':params['workspace_name'],
                    'objects':[
                        {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance  # DEBUG
                        }
                        ]
                    })[0]

            self.log(console,"BUILDING RETURN OBJECT")
            returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
            self.log(console,"psiBLAST_msa_start_Search DONE")
            return [returnVal]


        # FORMAT DB
        #
        # OLD SYNTAX: formatdb -i $database -o T -p F -> $database.nsq or $database.00.nsq
        # NEW SYNTAX: makeblastdb -in $database -parse_seqids -dbtype prot/nucl -out <basename>
        makeblastdb_cmd = [self.Make_BLAST_DB]

        # check for necessary files
        if not os.path.isfile(self.Make_BLAST_DB):
            raise ValueError("no such file '"+self.Make_BLAST_DB+"'")
        if not os.path.isfile(many_forward_reads_file_path):
            raise ValueError("no such file '"+many_forward_reads_file_path+"'")
        elif not os.path.getsize(many_forward_reads_file_path) > 0:
            raise ValueError("empty file '"+many_forward_reads_file_path+"'")

        makeblastdb_cmd.append('-in')
        makeblastdb_cmd.append(many_forward_reads_file_path)
        makeblastdb_cmd.append('-parse_seqids')
        makeblastdb_cmd.append('-dbtype')
        makeblastdb_cmd.append('prot')
        makeblastdb_cmd.append('-out')
        makeblastdb_cmd.append(many_forward_reads_file_path)

        # Run Make_BLAST_DB, capture output as it happens
        #
        self.log(console, 'RUNNING Make_BLAST_DB:')
        self.log(console, '    '+' '.join(makeblastdb_cmd))
#        report += "\n"+'running Make_BLAST_DB:'+"\n"
#        report += '    '+' '.join(makeblastdb_cmd)+"\n"

        p = subprocess.Popen(makeblastdb_cmd, \
                             cwd = self.scratch, \
                             stdout = subprocess.PIPE, \
                             stderr = subprocess.STDOUT, \
                             shell = False)

        while True:
            line = p.stdout.readline()
            if not line: break
            self.log(console, line.replace('\n', ''))

        p.stdout.close()
        p.wait()
        self.log(console, 'return code: ' + str(p.returncode))
        if p.returncode != 0:
            raise ValueError('Error running makeblastdb, return code: '+str(p.returncode) + 
                '\n\n'+ '\n'.join(console))

        # Check for db output
        if not os.path.isfile(many_forward_reads_file_path+".psq") and not os.path.isfile(many_forward_reads_file_path+".00.psq"):
            raise ValueError("makeblastdb failed to create DB file '"+many_forward_reads_file_path+".psq'")
        elif not os.path.getsize(many_forward_reads_file_path+".psq") > 0 and not os.path.getsize(many_forward_reads_file_path+".00.psq") > 0:
            raise ValueError("makeblastdb created empty DB file '"+many_forward_reads_file_path+".psq'")


        ### Construct the psiBLAST command
        #
        # OLD SYNTAX: blastpgp -j <rounds> -h <e_value_matrix> -z <database_size:e.g. 1e8> -q $q -G $G -E $E -m $m -e $e_value -v $limit -b $limit -K $limit -i $fasta_file -B <msa_file> -d $database -o $out_file
        # NEW SYNTAX: psiblast -in_msa <msa_queryfile> -msa_master_idx <row_n> -db <basename> -out <out_aln_file> -outfmt 0/7 (8 became 7) -evalue <e_value> -dust no (DNA) -seg no (AA) -num_threads <num_cores>
        #
        blast_bin = self.psiBLAST
        blast_cmd = [blast_bin]

        # check for necessary files
        if not os.path.isfile(blast_bin):
            raise ValueError("no such file '"+blast_bin+"'")
        #if not os.path.isfile(one_forward_reads_file_path):
        #    raise ValueError("no such file '"+one_forward_reads_file_path+"'")
        #elif not os.path.getsize(one_forward_reads_file_path) > 0:
        #    raise ValueError("empty file '"+one_forward_reads_file_path+"'")
        if not os.path.isfile(input_MSA_file_path):
            raise ValueError("no such file '"+input_MSA_file_path+"'")
        elif not os.path.getsize(input_MSA_file_path):
            raise ValueError("empty file '"+input_MSA_file_path+"'")
        if not os.path.isfile(many_forward_reads_file_path):
            raise ValueError("no such file '"+many_forward_reads_file_path+"'")
        elif not os.path.getsize(many_forward_reads_file_path):
            raise ValueError("empty file '"+many_forward_reads_file_path+"'")

        # set the output path
        timestamp = int((datetime.utcnow() - datetime.utcfromtimestamp(0)).total_seconds()*1000)
        output_dir = os.path.join(self.scratch,'output.'+str(timestamp))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_aln_file_path = os.path.join(output_dir, 'alnout.txt');
        output_filtered_fasta_file_path = os.path.join(output_dir, 'output_filtered.fna');

        # this is command for basic search mode
#        blast_cmd.append('-query')
#        blast_cmd.append(one_forward_reads_file_path)
        blast_cmd.append('-in_msa')
        blast_cmd.append(input_MSA_file_path)
        blast_cmd.append('-msa_master_idx')
        blast_cmd.append(str(master_row_idx))
        blast_cmd.append('-db')
        blast_cmd.append(many_forward_reads_file_path)
        blast_cmd.append('-out')
        blast_cmd.append(output_aln_file_path)
        blast_cmd.append('-outfmt')
        blast_cmd.append('7')
        blast_cmd.append('-evalue')
        blast_cmd.append(str(params['e_value']))

        # options
        if 'maxaccepts' in params:
            if params['maxaccepts']:
                blast_cmd.append('-max_target_seqs')
                blast_cmd.append(str(params['maxaccepts']))

        # Run BLAST, capture output as it happens
        #
        self.log(console, 'RUNNING BLAST:')
        self.log(console, '    '+' '.join(blast_cmd))
#        report += "\n"+'running BLAST:'+"\n"
#        report += '    '+' '.join(blast_cmd)+"\n"

        p = subprocess.Popen(blast_cmd, \
                             cwd = self.scratch, \
                             stdout = subprocess.PIPE, \
                             stderr = subprocess.STDOUT, \
                             shell = False)

        while True:
            line = p.stdout.readline()
            if not line: break
            self.log(console, line.replace('\n', ''))

        p.stdout.close()
        p.wait()
        self.log(console, 'return code: ' + str(p.returncode))
        if p.returncode != 0:
            raise ValueError('Error running BLAST, return code: '+str(p.returncode) + 
                '\n\n'+ '\n'.join(console))


        # get query_len for filtering later
        #
        query_len = 0
        with open(one_forward_reads_file_path, 'r', 0) as query_file_handle:
            for line in query_file_handle:
                if line.startswith('>'):
                    continue
                query_len += len(re.sub(r" ","", line.rstrip())) 
        

        # Parse the BLAST tabular output and store ids to filter many set to make filtered object to save back to KBase
        #
        self.log(console, 'PARSING BLAST ALIGNMENT OUTPUT')
        if not os.path.isfile(output_aln_file_path):
            raise ValueError("failed to create BLAST output: "+output_aln_file_path)
        elif not os.path.getsize(output_aln_file_path) > 0:
            raise ValueError("created empty file for BLAST output: "+output_aln_file_path)
        hit_seq_ids = dict()
        output_aln_file_handle = open (output_aln_file_path, "r", 0)
        output_aln_buf = output_aln_file_handle.readlines()
        output_aln_file_handle.close()
        hit_total = 0
        high_bitscore_line = dict()
        high_bitscore_score = dict()
        high_bitscore_ident = dict()
        high_bitscore_alnlen = dict()
        hit_order = []
        hit_buf = []
        header_done = False
        for line in output_aln_buf:
            if line.startswith('#'):
                if not header_done:
                    hit_buf.append(line)
                continue
            header_done = True
            #self.log(console,'HIT LINE: '+line)  # DEBUG
            hit_info = line.split("\t")
            hit_seq_id     = hit_info[1]
            hit_ident      = float(hit_info[2]) / 100.0
            hit_aln_len    = hit_info[3]
            hit_mismatches = hit_info[4]
            hit_gaps       = hit_info[5]
            hit_q_beg      = hit_info[6]
            hit_q_end      = hit_info[7]
            hit_t_beg      = hit_info[8]
            hit_t_end      = hit_info[9]
            hit_e_value    = hit_info[10]
            hit_bitscore   = hit_info[11]

            # BLAST SOMETIMES ADDS THIS TO IDs.  NO IDEA WHY, BUT GET RID OF IT!
            if hit_seq_id.startswith('gnl|'):
                hit_seq_id = hit_seq_id[4:]

            try:
                if float(hit_bitscore) > float(high_bitscore_score[hit_seq_id]):
                    high_bitscore_score[hit_seq_id] = hit_bitscore
                    high_bitscore_ident[hit_seq_id] = hit_ident
                    high_bitscore_alnlen[hit_seq_id] = hit_aln_len
                    high_bitscore_line[hit_seq_id] = line
            except:
                hit_order.append(hit_seq_id)
                high_bitscore_score[hit_seq_id] = hit_bitscore
                high_bitscore_ident[hit_seq_id] = hit_ident
                high_bitscore_alnlen[hit_seq_id] = hit_aln_len
                high_bitscore_line[hit_seq_id] = line

        for hit_seq_id in hit_order:
            hit_buf.append(high_bitscore_line[hit_seq_id])

            #self.log(console,"HIT_SEQ_ID: '"+hit_seq_id+"'")
            if 'ident_thresh' in params and float(params['ident_thresh']) > float(high_bitscore_ident[hit_seq_id]):
                continue
            if 'bitscore' in params and float(params['bitscore']) > float(high_bitscore_score[hit_seq_id]):
                continue
            if 'overlap_fraction' in params and float(params['overlap_fraction']) > float(high_bitscore_alnlen[hit_seq_id])/float(query_len):
                continue
            
            hit_total += 1
            hit_seq_ids[hit_seq_id] = True
            self.log(console, "HIT: '"+hit_seq_id+"'")  # DEBUG
        

        self.log(console, 'EXTRACTING HITS FROM INPUT')
        self.log(console, 'MANY_TYPE_NAME: '+many_type_name)  # DEBUG


        # FeatureSet input -> FeatureSet output
        #
        if many_type_name == 'FeatureSet':

            seq_total = len(input_many_featureSet['elements'].keys())

            output_featureSet = dict()
            if 'description' in input_many_featureSet and input_many_featureSet['description'] != None:
                output_featureSet['description'] = input_many_featureSet['description'] + " - psiBLAST_msa_start_Search filtered"
            else:
                output_featureSet['description'] = "psiBLAST_msa_start_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()
            if 'element_ordering' in input_many_featureSet and input_many_featureSet['element_ordering'] != None:
                for fId in input_many_featureSet['element_ordering']:
                    try:
                        in_filtered_set = hit_seq_ids[fId]
                        #self.log(console, 'FOUND HIT '+fId)  # DEBUG
                        output_featureSet['element_ordering'].append(fId)
                        output_featureSet['elements'][fId] = input_many_featureSet['elements'][fId]
                    except:
                        pass
            else:
                fId_list = input_many_featureSet['elements'].keys()
                self.log(console,"ADDING FEATURES TO FEATURESET")
                for fId in sorted(fId_list):
                    try:
                        #self.log(console,"checking '"+fId+"'")
                        in_filtered_set = hit_seq_ids[fId]
                        #self.log(console, 'FOUND HIT '+fId)  # DEBUG
                        output_featureSet['element_ordering'].append(fId)
                        output_featureSet['elements'][fId] = input_many_featureSet['elements'][fId]
                    except:
                        pass

        # Parse Genome hits into FeatureSet
        #
        elif many_type_name == 'Genome':
            seq_total = 0

            output_featureSet = dict()
            if 'scientific_name' in input_many_genome and input_many_genome['scientific_name'] != None:
                output_featureSet['description'] = input_many_genome['scientific_name'] + " - psiBLAST_msa_start_Search filtered"
            else:
                output_featureSet['description'] = "psiBLAST_msa_start_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()
            for feature in input_many_genome['features']:
                seq_total += 1
                try:
                    in_filtered_set = hit_seq_ids[feature['id']]
                    #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
                    output_featureSet['element_ordering'].append(feature['id'])
                    output_featureSet['elements'][feature['id']] = [input_many_ref]
                except:
                    pass

        # Parse GenomeSet hits into FeatureSet
        #
        elif many_type_name == 'GenomeSet':
            seq_total = 0

            output_featureSet = dict()
            if 'description' in input_many_genomeSet and input_many_genomeSet['description'] != None:
                output_featureSet['description'] = input_many_genomeSet['description'] + " - psiBLAST_msa_start_Search filtered"
            else:
                output_featureSet['description'] = "psiBLAST_msa_start_Search filtered"
            output_featureSet['element_ordering'] = []
            output_featureSet['elements'] = dict()

            for genome_name in input_many_genomeSet['elements'].keys():
                if 'ref' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['ref'] != None:
                    genomeRef = input_many_genomeSet['elements'][genome_name]['ref']
                    genome = ws.get_objects([{'ref':genomeRef}])[0]['data']
                    for feature in genome['features']:
                        seq_total += 1
                        try:
                            in_filtered_set = hit_seq_ids[feature['id']]
                            #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
                            output_featureSet['element_ordering'].append(feature['id'])
                            output_featureSet['elements'][feature['id']] = [genomeRef]
                        except:
                            pass

                elif 'data' in input_many_genomeSet['elements'][genome_name] and \
                        input_many_genomeSet['elements'][genome_name]['data'] != None:
#                    genome = input_many_genomeSet['elements'][genome_name]['data']
#                    for feature in genome['features']:
#                        #self.log(console,"kbase_id: '"+feature['id']+"'")  # DEBUG
#                        seq_total += 1
#                        try:
#                            in_filtered_set = hit_seq_ids[feature['id']]
#                            #self.log(console, 'FOUND HIT: '+feature['id'])  # DEBUG
#                            output_featureSet['element_ordering'].append(feature['id'])
                    raise ValueError ("FAILURE: unable to address genome object that is stored within 'data' field of genomeSet object")
#                            output_featureSet['elements'][feature['id']] = [genomeRef_is_inside_data_within_genomeSet_object_and_that_cant_be_addressed]
#                        except:
#                            pass


        # load the method provenance from the context object
        #
        self.log(console,"SETTING PROVENANCE")  # DEBUG
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects'] = []
        if 'input_one_name' in params and params['input_one_name'] != None:
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_one_name'])
        provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_msa_name'])
        provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_many_name'])
        provenance[0]['service'] = 'kb_blast'
        provenance[0]['method'] = 'psiBLAST_msa_start_Search'


        # Upload results
        #
        if len(invalid_msgs) == 0:
            self.log(console,"UPLOADING RESULTS")  # DEBUG

            # input FeatureSet, Genome, and GenomeSet -> upload FeatureSet output
            new_obj_info = ws.save_objects({
                            'workspace': params['workspace_name'],
                            'objects':[{
                                    'type': 'KBaseCollections.FeatureSet',
                                    'data': output_featureSet,
                                    'name': params['output_filtered_name'],
                                    'meta': {},
                                    'provenance': provenance
                                }]
                        })

        # build output report object
        #
        self.log(console,"BUILDING REPORT")  # DEBUG
        if len(invalid_msgs) == 0:
            report += 'sequences in many set: '+str(seq_total)+"\n"
            report += 'sequences in hit set:  '+str(hit_total)+"\n"
            report += "\n"
            for line in hit_buf:
                report += line
            reportObj = {
                'objects_created':[{'ref':params['workspace_name']+'/'+params['output_filtered_name'], 'description':'psiBLAST_msa_start_Search hits'}],
                'text_message':report
                }
        else:
            report += "FAILURE\n\n"+"\n".join(invalid_msgs)+"\n"
            reportObj = {
                'objects_created':[],
                'text_message':report
                }

        reportName = 'blast_report_'+str(hex(uuid.getnode()))
        report_obj_info = ws.save_objects({
#                'id':info[6],
                'workspace':params['workspace_name'],
                'objects':[
                    {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance
                    }
                ]
            })[0]

        self.log(console,"BUILDING RETURN OBJECT")
#        returnVal = { 'output_report_name': reportName,
#                      'output_report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
#                      'output_filtered_ref': params['workspace_name']+'/'+params['output_filtered_name']
#                      }
        returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
        self.log(console,"psiBLAST_msa_start_Search DONE")
        #END psiBLAST_msa_start_Search

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method psiBLAST_msa_start_Search return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]
