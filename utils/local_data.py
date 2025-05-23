import os
import sys
from typing import Callable, Dict, List, Optional, Set

import pandas as pd

from derivative_columns.atr import add_tr_delta_col_to_ohlc

from utils.import_data import get_local_ticker_data_file_name, import_ohlc_yfinance

MUST_HAVE_DERIVATIVE_COLUMNS: Set[str] = {"tr", "tr_delta"}

# NOTE tr - True Range
# tr_delta is a must-have column
# because it is used in update_top_losses()


class TickersData:
    """
    This class stores OHLC data for tickers
    locally and delivers it as needed,
    instead of downloading it from the Internet.
    """

    # NOTE
    # Practice has shown that it is advisable to maintain raw OHLC data,
    # as well as data with added derivative columns and features, in separate files.
    # You'll see the code saves single_raw_XXX.xlsx and single_with_features_XXX.xlsx files.

    # You will often change derived columns and features.
    # In such cases, you only need to delete single_with_features_XXX.xlsx files
    # so that the system creates derivative columns and features again.
    # And it won't have to request the raw OHLC data from the provider again.

    def __init__(
        self,
        tickers: List[str],
        add_feature_cols_func: Callable,
        import_ohlc_func: Callable = import_ohlc_yfinance,
        recreate_columns_every_time: bool = False,
    ):
        """
        Fill self.tickers_data_with_features
        to serve the get_data() calls.
        Also, save the inputs, because we may need them later.
        """
        self.tickers_data_with_features: Dict[str, pd.DataFrame] = dict()
        self.add_feature_cols_func = add_feature_cols_func
        self.import_ohlc_func = import_ohlc_func
        self.recreate_columns_every_time = recreate_columns_every_time
        for ticker in tickers:
            df = self.get_df_with_features(ticker=ticker)

            # All columns of MUST_HAVE_DERIVATIVE_COLUMNS
            # are essential for running backtests,
            # so ensure DataFrame has them
            for col in MUST_HAVE_DERIVATIVE_COLUMNS:
                if col not in df.columns:
                    df = add_tr_delta_col_to_ohlc(ohlc_df=df)

            self.tickers_data_with_features[ticker] = df
            
    def _read_raw_data_from_xlsx(self) -> Optional[pd.DataFrame]:
        if os.path.exists(self.filename_raw) and os.path.getsize(self.filename_raw) > 0:
            df = pd.read_excel(self.filename_raw, index_col=0)
            df = df[["Open", "High", "Low", "Close", "Volume"]]
            df = self.add_feature_cols_func(df=df)
            if not self.recreate_columns_every_time:
                directory = os.path.dirname(self.filename_with_features) or "."
                directory = os.path.normpath(directory)
                full_directory_path = os.path.abspath(directory)
                print(f"Attempting to create directory: {full_directory_path}")
                os.makedirs(full_directory_path, exist_ok=True)
                if not os.path.exists(full_directory_path):
                    raise RuntimeError(f"Failed to create directory: {full_directory_path}")
                print(f"Saving to: {self.filename_with_features}")
                df.to_excel(self.filename_with_features)
                print(f"Saved {self.filename_with_features} - OK")
            print(f"Reading {self.filename_raw} - OK")
            return df
        return None        
    
    def _import_data_from_external_provider(self, ticker: str) -> pd.DataFrame:
        """
        Try to request OHLC data from an external provider.
        If it fails, raise an exception.
        If it succeeds, add additional columns to the data,
        save local Excel cache files, and return the DataFrame.
        """
        print(
            f"Running {self.import_ohlc_func.__name__} for {ticker=}...",
            file=sys.stderr,
        )
        df = self.import_ohlc_func(ticker=ticker)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            error_msg = f"get_df_with_features: failed call of {self.import_ohlc_func} for {ticker=}, returned {df=}"
            raise RuntimeError(error_msg)
        # Ensure the directory exists before saving
        directory = os.path.dirname(self.filename_raw) or "."
        directory = os.path.normpath(directory)
        full_directory_path = os.path.abspath(directory)
        print(f"Current working directory: {os.getcwd()}")
        print(f"Attempting to create directory: {full_directory_path}")
        os.makedirs(full_directory_path, exist_ok=True)
        if not os.path.exists(full_directory_path):
            raise RuntimeError(f"Failed to create directory: {full_directory_path}")
        print(f"Saving to: {self.filename_raw}")
        df.to_excel(self.filename_raw)
        print(f"Saved {self.filename_raw} - OK")
        df = self.add_feature_cols_func(df=df)
        if not self.recreate_columns_every_time:
            # Directory already created above, but ensure for with_features file
            directory = os.path.dirname(self.filename_with_features) or "."
            directory = os.path.normpath(directory)
            full_directory_path = os.path.abspath(directory)
            print(f"Attempting to create directory: {full_directory_path}")
            os.makedirs(full_directory_path, exist_ok=True)
            if not os.path.exists(full_directory_path):
                raise RuntimeError(f"Failed to create directory: {full_directory_path}")
            print(f"Saving to: {self.filename_with_features}")
            df.to_excel(self.filename_with_features)
            print(f"Saved {self.filename_with_features} - OK")
        return df
   

    def get_df_with_features(self, ticker: str) -> pd.DataFrame:
        """
        1. Try to read OHLC data with additional columns from local XLSX file.
        If OK, check data and return it.

        2. Try to read raw OHLC data from local XLSX file.
        If OK, call self.add_feature_cols_func, check data, save local XLSX file, and return DataFrame.

        3. If reading data from local XLSX files failed, call self.import_ohlc_func and then self.add_feature_cols_func.
        Check the result. Save local XLSX files with raw data and with added features. Return DataFrame.
        """

        self.filename_with_features = get_local_ticker_data_file_name(
            ticker=ticker, data_type="with_features"
        )

        # if self.recreate_columns_every_time is True -
        # don't use locally cached derived columns,
        # recreate them every time,
        # i.e. don't try to read self.filename_with_features.

        # This is needed for cases when the add_feature_cols_func function
        # is called with different parameters,
        # in order to optimize these parameters.
        # See also the run_strategy_main_optimize.py file.

        if self.recreate_columns_every_time is False:
            if (
                os.path.exists(self.filename_with_features)
                and os.path.getsize(self.filename_with_features) > 0
            ):
                df = pd.read_excel(self.filename_with_features, index_col=0)
                print(f"Reading {self.filename_with_features} - OK")
                return df

        # self.recreate_columns_every_time is True
        # or failed to get data from self.filename_with_features

        self.filename_raw = get_local_ticker_data_file_name(
            ticker=ticker, data_type="raw"
        )
        res = self._read_raw_data_from_xlsx()
        if res is not None:
            return res

        # self.recreate_columns_every_time is True
        # or failed to get data from self.filename_with_features
        # and failed to get data from self.filename_raw

        return self._import_data_from_external_provider(ticker=ticker)

    def get_data(self, ticker: str) -> pd.DataFrame:
        """
        Try to get the corresponding DataFrame
        for ticker from self.tickers_data_with_features.
        If it is not possible, fill the corresponding key-value pair
        by calling get_df_with_features(ticker=ticker).
        """
        if (
            self.tickers_data_with_features
            and ticker in self.tickers_data_with_features
        ):
            return self.tickers_data_with_features[ticker]
        self.tickers_data_with_features[ticker] = self.get_df_with_features(
            ticker=ticker
        )
        return self.tickers_data_with_features[ticker]
