import logging
from pathlib import Path
import pandas as pd
from .helpers import make_string_BIDS_value_compliant

logger = logging.getLogger(__name__)

class Labels():
    def __init__(self, p=None):
        if not p is None:
            self.p_labels = Path(p)
            self.labels_df = self._read_labels(p)
        else:
            self.p_labels = None
            df = pd.DataFrame(columns=['roi_id', 'roi_name', 'abbreviation'])
            self.labels_df = df

    @staticmethod
    def _read_labels(p: Path):
        ext  = p.name.split('.')[-1]
        labels=None
        if ext == 'csv':
            labels = pd.read_csv(p, delimiter=',', header=None)
        elif ext == 'tsv':
            labels = pd.read_csv(p, delimiter='\t', header=None)
        else:
            logger.fatal(f"Cannot read labels file '{p}'; expect 'csv' or 'tsv' file.")

        if labels is not None:
            if len(labels.columns)==2:
                labels.columns = ['roi_id', 'roi_name']
                labels['abbreviation'] = labels.roi_name
            elif len(labels.columns)==3:
                labels.columns = ['roi_id', 'roi_name', 'abbreviation']
            else:
                logger.fatal(f"Labels file '{p}' contains {len(labels.columns)} columns; only 2 or 3 expected")
        return labels

    def generate_abbreviations_from_names(self, fct=make_string_BIDS_value_compliant):
        self.labels_df['abbreviation'] = self.labels_df.abbreviation.apply(lambda x: fct(x))

    def write_labels(self, p: Path):
        ext = p.name.split('.')[-1]
        if ext == 'csv':
            self.labels_df.sort_values('roi_id', ascending=True).to_csv(p.as_posix(), sep=',', header=None, index=False)
        elif ext == 'tsv':
            self.labels_df.sort_values('roi_id', ascending=True).to_csv(p.as_posix(), sep='\t', header=None, index=False)
        else:
            logger.fatal(f"Filetype '{ext}' not defined.")

    @staticmethod
    def get_from_df(df: pd.DataFrame, column_to_search: str, column_to_return: str, search_str,
                    case_sensitive=False, is_regexp=False, allow_multiple=False):
        if isinstance(search_str, str) & (case_sensitive==False) & (is_regexp==False):
            df_sel = df.loc[(df[column_to_search] == search_str) | (df[column_to_return].apply(lambda x: str(x).lower()) == search_str) | (df[column_to_return] == search_str.lower())]
        elif isinstance(search_str, str) & (is_regexp==False):
            df_sel = df.loc[(df[column_to_search] == search_str)]
        elif isinstance(search_str, str) & (is_regexp==True):
            df_sel = df.loc[df[column_to_search].str.contains(search_str, case=case_sensitive)]
        else: # search_str is not string, e.g. when querying ROI id
            df_sel = df.loc[(df[column_to_search] == search_str)]
        if column_to_return == 'index':
            values = df_sel.index
        else:
            values = df_sel[column_to_return].values
        if len(values)==1:
           return values[0]
        elif len(values)==0:
            logger.warning(f"Found no match")
        elif (len(values)>1) and allow_multiple:
            return values.tolist()
        else:
            logger.warning(f"Found {len(values)} item; only 1 expected")

    def get_roi_id_from_name(self, name:str, **kwargs):
        val = self.get_from_df(self.labels_df, 'roi_name', 'roi_id', search_str=name, **kwargs)
        return val

    def get_roi_id_from_abbreviation(self, abbreviation: str, **kwargs):
        val = self.get_from_df(self.labels_df, 'abbreviation', 'roi_id', search_str=abbreviation, **kwargs)
        return val

    def get_name_from_roi_id(self, roi_id: int):
        val = self.get_from_df(self.labels_df, 'roi_id', 'roi_name', search_str=roi_id)
        return val

    def get_abbreviation_from_roi_id(self, roi_id: int):
        val = self.get_from_df(self.labels_df, 'roi_id', 'abbreviation', search_str=roi_id)
        return val

    def remove_roi_id(self, roi_id: int):
        index = self.get_from_df(self.labels_df, 'roi_id', 'index', search_str=roi_id)
        if index is not None:
            logger.debug(f"Removing roi {roi_id} (idx={index}) from labels df")
            self.labels_df.drop(index=index, inplace=True)
            self.labels_df.reindex()
        else:
            logger.warning(f"ROI does not exist")

    def add_roi(self, name: str, roi_id=None, abbreviation=None, overwrite=False):
        if abbreviation is None:
            abbreviation = name
        if roi_id is None:
            roi_id = self.get_max_roi_id()
            if roi_id is None: # happens if there is no other roi in labels
                roi_id=1
            else:
                roi_id = roi_id + 1
            logger.warning(f"No ROI specified, using next free ROI ID {roi_id}")
        elif (roi_id in self.get_roi_ids()) and not overwrite:
            logger.fatal(f"ROI ID {roi_id} already used. Cannot add ROI -> Remove existing ROI or change ID")
            roi_id = None
        elif (roi_id in self.get_roi_ids()) and overwrite:
            logger.info(f"ROI ID {roi_id} already used. Will overwrite")
        else:
            logger.info(f"Adding ROI ID {roi_id} with name '{name}'.")
        if roi_id is not None:
            if self.labels_df.empty:
                index_cond = 0
            elif roi_id in self.labels_df.roi_id.unique().tolist(): # roi_id exists and to be overwritten
                index_cond = (self.labels_df.roi_id==roi_id)
            else: #new roi to be appended
                index_cond = self.labels_df.index.max()+1
            self.labels_df.loc[index_cond,:] = [int(roi_id), name, abbreviation]
            self.labels_df.roi_id = self.labels_df.roi_id.astype(int)

    def rename_roi(self, roi_id: int, name_new: str, abbreviation_new = None):
        if abbreviation_new is None:
            abbreviation_new = name_new
        self.remove_roi_id(roi_id)
        self.add_roi(name=name_new, roi_id=roi_id, abbreviation=abbreviation_new)

    def rename_rois(self, query_rename_map={}, query_in='name_abbreviation', case_sensitive=False, is_regexp=False):
        rois_renamed = []
        for regexp, new_name in query_rename_map.items():
            roi_id_name = self.get_roi_id_from_name(regexp, case_sensitive=case_sensitive,
                                                            is_regexp=is_regexp, allow_multiple=True)
            roi_id_abbr = self.get_roi_id_from_abbreviation(regexp, case_sensitive=case_sensitive,
                                                            is_regexp=is_regexp, allow_multiple=True)
            if query_in not in ['name_abbreviation', 'name', 'abbreviation']:
                query_in = 'name_abbreviation'
                logger.warning(f"{query_in} is not a valid option for 'query_in', using 'name_abbreviation'")
            if query_in=='name_abbreviation':
                if (roi_id_name is not None) and (roi_id_abbr is not None) :
                    if roi_id_name != roi_id_abbr:
                        logger.warning('Search in name and abbreviation returned different results: ')
                        logger.warning(f' - name         -> id {roi_id_name}')
                        logger.warning(f' - abbreviation -> id {roi_id_abbr}')
                        logger.warning(f'... using abbreviation -> id {roi_id_abbr}')
                    roi_id = roi_id_abbr
                elif (roi_id_name is not None) and (roi_id_abbr is None):
                    roi_id = roi_id_name
                elif (roi_id_name is None) and (roi_id_abbr is not None):
                    roi_id = roi_id_abbr
                else:
                    roi_id = None
            elif query_in=='name':
                roi_id = roi_id_name
            elif query_in=='abbreviation':
                roi_id = roi_id_abbr

            if isinstance(roi_id, list):
                for i, roi_id_inst in enumerate(roi_id):
                    name_inst = f"{new_name}_{i}"
                    self.rename_roi(roi_id_inst, name_new=name_inst, abbreviation_new=name_inst)
                    rois_renamed.append(roi_id_inst)
            elif roi_id is not None:
                self.rename_roi(roi_id, name_new=new_name, abbreviation_new=new_name)
                rois_renamed.append(roi_id)
            else:
                logger.warning(f"Could not find ROI using regexp '{regexp}'")
        return rois_renamed

    def swap_roi_ids(self, roi_id_old: int, roi_id_new: int):
        name = self.get_name_from_roi_id(roi_id_old)
        abbreviation = self.get_abbreviation_from_roi_id(roi_id_old)
        self.remove_roi_id(roi_id_old)
        self.add_roi(name=name, roi_id=roi_id_new, abbreviation=abbreviation)

    def get_roi_ids(self):
        roi_ids = self.labels_df.roi_id.unique().tolist()
        roi_ids.sort()
        return roi_ids

    def get_max_roi_id(self):
        if len(self.get_roi_ids()) == 0:
            max_id = None
        else:
            max_id = max(self.get_roi_ids())
        return max_id
