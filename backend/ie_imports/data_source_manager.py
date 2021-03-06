from abc import ABCMeta, abstractmethod
from typing import List, Union
import pandas as pd
import numpy as np

from backend import case_sensitive
from backend.common.helper import create_dictionary, Memoize2, obtain_dataset_source, \
    get_dataframe_copy_with_lowercase_multiindex
from backend.models.statistical_datasets import DataSource, Database, Dataset
from backend.models.musiasem_methodology_support import force_load


class IDataSourceManager(metaclass=ABCMeta):
    @abstractmethod
    def get_name(self) -> str:
        """ Source name """
        pass

    @abstractmethod
    def get_datasource(self) -> DataSource:
        """ Data source """
        pass

    @abstractmethod
    def get_databases(self) -> List[Database]:
        """ List of databases in the data source """
        pass

    @abstractmethod
    def get_datasets(self, database=None) -> list:
        """ List of datasets in a database, or in all the datasource (if database==None)
            Return a list of tuples (database, dataset)
        """
        pass

    @abstractmethod
    def get_dataset_structure(self, database, dataset) -> Dataset:
        """ Obtain the structure of a dataset: concepts, dimensions, attributes and measures """
        pass

    @abstractmethod
    def etl_full_database(self, database=None, update=False):
        """ If bulk download is supported, refresh full database """
        pass

    @abstractmethod
    def etl_dataset(self, dataset, update=False) -> Dataset:
        """ If bulk download is supported, refresh full dataset """
        pass

    @abstractmethod
    def get_dataset_filtered(self, dataset, dataset_params: list) -> Dataset:
        """ Obtains the dataset with its structure plus the filtered values
            The values can be in a pd.DataFrame or in JSONStat compact format
            After this, new dimensions can be joined, aggregations need to be performed
        """
        pass

    @abstractmethod
    def get_refresh_policy(self):  # Refresh frequency for list of databases, list of datasets, and dataset
        pass


class DataSourceManager:

    def __init__(self, session_factory):
        self.registry = create_dictionary()
        self._session_factory = session_factory

    # ---------------------------------------------------------------------------------
    def update_sources(self):
        """ Update bulk downloads for sources allowing full database. Not full dataset (on demand) """
        for s in self.registry:
            # Check last update
            poli = self.registry[s].get_refresh_policy()
            update = False
            if update:
                pass

    def register_datasource_manager(self, instance: IDataSourceManager):
        self.registry[instance.get_name()] = instance

    def unregister_datasource_manager(self, instance: IDataSourceManager):
        """
        Remove a data source
        This is necessary for AdHocDatasets which has to be created and deleted depending on needs
        (it is an Adapter of a map of the Datasets in the current state)

        :param instance:
        :return:
        """
        n = instance.get_name()
        if n in self.registry:
            del self.registry[instance.get_name()]

    def update_data_source(self, source: IDataSourceManager):
        # TODO Clear database
        # TODO Read structure of ALL datasets from this source
        pass

    def _get_source_manager(self, source):
        if source:
            if isinstance(source, str):
                if source in self.registry:
                    source = self.registry[source]
        return source

    # ---------------------------------------------------------------------------------

    def get_supported_sources(self):
        return [s for s in self.registry]
        # e.g.: return ["Eurostat", "SSP"]

    def get_databases(self, source: Union[IDataSourceManager, str]):
        # List of databases in source (a database contains one or more datasets)
        if source:
            source = self._get_source_manager(source)

        if not source:
            lst = []
            for s in self.registry:
                lst.extend([(s,
                             [db for db in self.registry[s].get_databases()]
                             )
                            ]
                           )
            return lst
        else:
            return [(source.get_name(),
                     [db for db in source.get_databases()]
                     )
                    ]

    # @cachier(stale_after=datetime.timedelta(days=1))
    @Memoize2
    def get_datasets(self, source: Union[IDataSourceManager, str]=None, database=None):
        """
        Obtain a list of tuples (Source, Dataset name)

        :param source: If specified, the name of the source
        :param database: If specified, the name of a database in the source
        :return: List of tuples (Source name, Dataset name)
        """
        if source:
            source = self._get_source_manager(source)

        if source:
            if database:  # SOURCE+DATABASE DATASETS
                return [(source.get_name(), source.get_datasets(database))]
            else:  # ALL SOURCE DATASETS
                lst = []
                for db in source.get_databases():
                    lst.extend(source.get_datasets(db))
                return [(source.get_name(), lst)]  # List of tuples (dataset code, description, urn)
        else:  # ALL DATASETS
            lst = []
            for s in self.registry:
                lst.append((s, [ds for ds in self.registry[s].get_datasets()]))
            return lst  # List of tuples (source, dataset code, description, urn)

    def get_dataset_structure(self, source: Union[IDataSourceManager, str], dataset: str) -> Dataset:
        """ Obtain the structure of a dataset, a list of dimensions and measures, without data """
        if not source:
            source = obtain_dataset_source(dataset)
            if not source:
                raise Exception("Could not find a Source containing the Dataset '"+dataset+"'")

        source = self._get_source_manager(source)
        return source.get_dataset_structure(None, dataset)

    def get_dataset_filtered(self, source: Union[IDataSourceManager, str], dataset: str, dataset_params: dict) -> Dataset:
        """ Obtain the structure of a dataset, and DATA according to the specified FILTER, dataset_params """
        source = self._get_source_manager(source)
        return source.get_dataset_filtered(dataset, dataset_params)

# --------------------------------------------------------------------------------------------------------------------


def get_dataset_structure(session_factory, source: IDataSourceManager, dataset: str) -> Dataset:
    """ Helper function called by IDataSourceManager implementations """

    src_name = source.get_name()

    # ACCESS TO METADATA DATABASE
    session = session_factory()
    # Check if the source exists. Create it if not
    src = session.query(DataSource).filter(DataSource.name == src_name).first()
    if not src:
        src = source.get_datasource()
        session.add(src)
    # Check if the dataset exists. "ETL" it if not
    ds = session.query(Dataset).\
        filter(Dataset.code == dataset).\
        join(Dataset.database).join(Database.data_source).\
        filter(DataSource.name == src_name).first()
    if not ds:
        # >>>> It may imply a full ETL operation <<<<
        ds = source.etl_dataset(dataset, update=False)
        # Use existing database
        db = session.query(Database).filter(Database.code == ds.database.code).first()
        if db:
            ds.database = db
        else:
            ds.database.data_source = src  # Assign the DataSource to the Database
        session.add(ds)

    session.commit()

    force_load(ds)

    session.close()
    session_factory.remove()
    # END OF ACCESS TO DATABASE

    return ds


def filter_dataset_into_dataframe(in_df, filter_dict, eurostat_postprocessing=False):
    """
    Function allowing filtering a dataframe passed as input,
    using the information from "filter_dict", containing the dimension names and the list
    of codes that should pass the filter. If several dimensions are specified an AND combination
    is done

    "in_df" must have as index a MultiIndex with all the dimensions appearing in the "filter_dict"


    :param in_df: Input dataset, pd.DataFrame
    :param filter_dict: A dictionary with the items to keep, per dimension
    :param eurostat_postprocessing: Eurostat dataframe needs special postprocessing. If True, do it
    :return: Filtered dataframe
    """

    # TODO If a join is requested, do it now. Add a new element to the INDEX
    # TODO The filter params can contain a filter related to the new joins

    start = None
    if "StartPeriod" in filter_dict:
        start = filter_dict["StartPeriod"]
        if isinstance(start, list): start = start[0]
    if "EndPeriod" in filter_dict:
        endd = filter_dict["EndPeriod"]
        if isinstance(endd, list): endd = endd[0]
    else:
        if start:
            endd = start
    if not start:
        columns = in_df.columns  # All columns
    else:
        # Assume year, convert to integer, generate range, then back to string
        start = int(start)
        endd = int(endd)
        columns = [str(a) for a in range(start, endd + 1)]

    if not case_sensitive:
        in_df_lower = get_dataframe_copy_with_lowercase_multiindex(in_df)

    # Rows (dimensions)
    cond_accum = np.full(in_df.index.size, fill_value=True)
    for i, k in enumerate(in_df.index.names):
        if k in filter_dict:
            lst = filter_dict[k]
            if not isinstance(lst, list):
                lst = [lst]
            if len(lst) > 0:
                if not case_sensitive:
                    cond_accum &= in_df_lower.index.isin([str(l).lower() for l in lst], i)
                else:
                    cond_accum &= in_df.index.isin([str(l) for l in lst], i)
            else:
                cond_accum &= in_df[in_df.columns[0]] == in_df[in_df.columns[0]]

    # Remove non existent index values
    for v in columns.copy():
        if v not in in_df.columns:
            columns.remove(v)

    tmp = in_df[columns][cond_accum]

    # Convert columns to a single column "TIME_PERIOD"
    if eurostat_postprocessing:
        if len(tmp.columns) > 0:
            lst = []
            for i, cn in enumerate(tmp.columns):
                df2 = tmp[[cn]].copy(deep=True)
                # TODO: use column name from metadata instead of hardcoded "value"
                df2.columns = ["value"]
                df2["TIME_PERIOD"] = cn
                lst.append(df2)
            in_df = pd.concat(lst)
            in_df.reset_index(inplace=True)
            # Value column should be last column
            lst = [l for l in in_df.columns]
            for i, l in enumerate(lst):
                if l == "value":
                    lst[-1], lst[i] = lst[i], lst[-1]
                    break
            in_df = in_df.reindex(lst, axis=1)
            return in_df
        else:
            return None
    else:
        tmp.reset_index(inplace=True)
        if len(tmp.columns) > 0:
            return tmp
        else:
            return None
