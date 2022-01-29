'''
Database library for VCP screener
'''

from pandas_datareader import data as pdr
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, date
import numpy as np
import sys
import os
import time

from stock_vcpscreener.vcp_util.util import get_last_trade_day, convert_strdate_datetime
pd.options.mode.chained_assignment = None


def volume_check():
    '''
    Yfinance often gives us wrong volume that is 100x its actual value
    Need to work out a way to check the two libraries
    '''
    pass


def create_index_database(csvdir_name, source):
    '''
    Download S&P500 index and save result as csv
    '''
    outfilename = 'GSPC_SP500.csv'
    trade_day = get_last_trade_day()

    if source == 'yfinance':
        index = '^GSPC'
    elif source == 'stooq':
        index = '^SPX'       #SPX and SPY represent options on the S&P 500 index
    else:
        print('Please select either yfinance or stooq')

    start_date = trade_day.date() - timedelta(days=365 + 7)
    end_date = trade_day.date() + timedelta(days=1)         #+1 to include the current day

    if not os.path.exists(csvdir_name+outfilename):
        print(f"Downloading index data to {outfilename}")
        try:
            if source == 'yfinance':
                yf.pdr_override()
                df = pdr.get_data_yahoo(index, start=start_date, end=end_date)
            elif source == 'stooq':
                df = pdr.DataReader(index, 'stooq', start=start_date, end=end_date)
            df.to_csv(csvdir_name+outfilename)

        except Exception as inst:
            print(inst)
    else:
        print(f"File {outfilename} exists")


def get_index_lastday(csvdir_name):
    '''
    Return the most updated date of the index csv file
    '''
    infilename = 'GSPC_SP500.csv'

    if os.path.exists(csvdir_name+infilename):
        indexdata = pd.read_csv(csvdir_name+infilename, header=0)
        indexdata['Date'] = pd.to_datetime(indexdata['Date'])
        indexdata.set_index('Date', inplace=True)
        last_avail_date = indexdata.index[-1]
    else:
        last_avail_date = 'N/A'

    return last_avail_date


def update_index_database(csvdir_name, source, trade_day):
    '''
    Read in csv for the S&P500 index, check the last updated date and update accordingly
    '''
    infilename = 'GSPC_SP500.csv'
    # trade_day = get_last_trade_day().date()

    if source == 'yfinance':
        index = '^GSPC'
    elif source == 'stooq':
        index = '^SPX'
    else:
        print('Please select either yfinance or stooq')

    if os.path.exists(csvdir_name+infilename):
        indexdata = pd.read_csv(csvdir_name+infilename, header=0)
        indexdata['Date'] = pd.to_datetime(indexdata['Date'])
        indexdata.set_index('Date', inplace=True)
        last_avail_date = indexdata.index[-1]

        if (trade_day - last_avail_date.date()).days > 0:
            print(f"Updating index data to {infilename}")
            try:
                if source == 'yfinance':
                    yf.pdr_override()
                    df = pdr.get_data_yahoo(index, start=last_avail_date.date()-timedelta(days=15), end=trade_day+timedelta(days=1), pause=1)  # Get two weeks back
                elif source == 'stooq':
                    df = pdr.DataReader(index, 'stooq', start=last_avail_date.date()-timedelta(days=15), end=trade_day+timedelta(days=1))
                indexdata = pd.concat([indexdata, df])

                # Check if the Volume column of the new data is identical to the one in the db
                check = indexdata.groupby(indexdata.index)['Volume'].nunique().ne(1)
                if sum(check) != 0:
                    # Now set everything to be the minimum of the duplicated
                    indexdata['Volume'] = indexdata.groupby(indexdata.index)['Volume'].transform('min')

                indexdata = indexdata[~indexdata.index.duplicated(keep='first')]
                indexdata = indexdata.sort_index()
                indexdata.to_csv(csvdir_name+infilename, mode='w')

                # Determine if the data is not updated or not
                updated_last_avail_date = indexdata.index[-1]
                if (trade_day - updated_last_avail_date.date()).days > 0:
                    print("Please wait until yahoo finance update today's data.")
                    sys.exit(0)

            except Exception as inst:
                print(inst)
                print('Update failed')
        else:
            print(f"No update needed")
    else:
        print('File not found!')


def get_stock_data_specific_date(csvdir_name, stock, in_date, minmax_range=False, percent_change=False):
    '''
    Return the OHLC df of a specific stock of a given date
    '''
    infilename = stock.strip().ljust(5,'_')+'.csv'

    if not isinstance(in_date, date):
        in_date = convert_strdate_datetime(in_date)

    if os.path.exists(csvdir_name+infilename):
        df = pd.read_csv(csvdir_name+infilename, header=0)
        df['Date'] = pd.to_datetime(df['Date'],format='%Y-%m-%d')
        df['Dateonly'] = df['Date']
        df.set_index('Date', inplace=True)
        
        in_date = datetime.combine(in_date, datetime.min.time()) 

        #if in_date in df.index:
        try:
            sel_df = df.loc[in_date]
            sel_df['Ticker'] = stock.strip()
            print('debug1')

            if percent_change:
                tmp_df = df[df['Dateonly'] <= in_date]
                sel_df['Change'] = tmp_df['Adj Close'].iloc[-1] - tmp_df['Adj Close'].iloc[-2]
                sel_df['Change (%)'] = (tmp_df['Adj Close'].iloc[-1] - tmp_df['Adj Close'].iloc[-2]) / tmp_df['Adj Close'].iloc[-2]
            print('debug2')
            if minmax_range:
                sel_df['52 Week Min'] = min(df['Adj Close'].loc[in_date - timedelta(days=365): in_date])
                sel_df['52 Week Max'] = max(df['Adj Close'].loc[in_date - timedelta(days=365): in_date])

            print('debug3')
            sel_df = sel_df.drop('Dateonly')
        except Exception as e:
            print('Specified date not in the data with error ', e)
            return np.nan
    else:
        print('Stock not available')
        return np.nan

    return sel_df


def create_stock_database(stock_list, csvdir_name, source):
    '''
    Download stock data and save them as csv
    '''
    trade_day = get_last_trade_day()

    # Read in the database update date
    if os.path.exists(csvdir_name+"last_update.dat"):
        lastupdate = pd.read_csv(csvdir_name+"last_update.dat", header=0)
        lastupdate['Date']=pd.to_datetime(lastupdate['Date'])
        lastupdate_day = lastupdate['Date'][0]
    else:
        lastupdate = pd.DataFrame([trade_day.date() - timedelta(days=365+7)], columns=['Date'])
        lastupdate_day = lastupdate['Date'][0]

    # Read in the companylist.csv
    # data = pd.read_csv("Tickers.csv", header=0)
    # stock_list = list(data.Symbol)

    for stock in stock_list:
        outfilename = stock.strip().ljust(5,'_')+'.csv'
        start_date = trade_day.date() - timedelta(days=365 + 7)     # Do one years and 7 days
        end_date = trade_day.date() +timedelta(days=1)
        if not os.path.exists(csvdir_name+outfilename):
            print(f"Downloading info on {stock} to {outfilename}")
            try:
                if source == 'yfinance':
                    yf.pdr_override()
                    df = pdr.get_data_yahoo(stock, start=start_date, end=end_date)
                elif source == 'stooq':
                    df = pdr.DataReader(stock.strip(), 'stooq', start=start_date, end=end_date)
                if df.empty:
                    with open(csvdir_name+stock.strip().ljust(5,'_')+'.txt', 'w') as out_file:
                        out_file.write('Empty dataframe\n')
                        out_file.write(f'Last try on {end_date}')
                else:
                    df.to_csv(csvdir_name+outfilename)

            except Exception as inst:
                print(inst)
                with open(csvdir_name+stock.strip().ljust(5,'_')+'.txt', 'w') as out_file:
                    out_file.write(str(inst))
                    out_file.write(f'Last try on {end_date}')
        else:
            print(f"File {outfilename} exists")

    # When done, update the last update csv file to current time (UTC-5)
    lastupdate['Date'] = (datetime.utcnow() - timedelta(hours=5)).date()
    lastupdate.to_csv(csvdir_name+"last_update.dat", mode='w',index=False)



def update_stock_database(stock_list, csvdir_name, source, trade_day, override=False):
    '''
    Read in csv for each stock, check the last updated date and update accordingly
    '''
    # trade_day = get_last_trade_day().date()

    # Read in the database update date
    lastupdate = pd.read_csv(csvdir_name+"last_update.dat", header=0)
    lastupdate['Date']=pd.to_datetime(lastupdate['Date'])
    lastupdate_day = lastupdate['Date'][0]

    if (trade_day - lastupdate_day.date()).days > 0 or override:

        # Read in the companylist.csv
        # data = pd.read_csv("Tickers.csv", header=0)
        # stock_list = list(data.Symbol)

        for stock in stock_list:

            # if stock[0:1] <'S':
            #     continue

            infilename = stock.strip().ljust(5,'_')+'.csv'

            if os.path.exists(csvdir_name+infilename):

                stockdata = pd.read_csv(csvdir_name+infilename, header=0)
                stockdata['Date'] = pd.to_datetime(stockdata['Date'])
                stockdata.set_index('Date', inplace=True)

                # Check if the last line contains Nan:
                if np.isnan(stockdata.iloc[-1]['Open']) or np.isnan(stockdata.iloc[-1]['Volume']):
                    stockdata = stockdata[:-1]

                last_avail_date = stockdata.index[-1]

                if (trade_day - last_avail_date.date()).days > 0:
                    # print((trade_day.date() - last_avail_date.date()).days)
                    print(f"Updating info on {stock} on {infilename}")
                    try:
                        if source == 'yfinance':
                            yf.pdr_override()
                            df = pdr.get_data_yahoo(stock, start=last_avail_date.date()-timedelta(days=15), end=trade_day+timedelta(days=1))  #  pause=1 Get two weeks back
                        elif source == 'stooq':
                            df = pdr.DataReader(stock.strip(), 'stooq', start=last_avail_date.date()-timedelta(days=15), end=trade_day+timedelta(days=1))
                        stockdata = pd.concat([stockdata, df])

                        # Check if the Volume column of the new data is identical to the one in the db
                        check = stockdata.groupby(stockdata.index)['Volume'].nunique().ne(1)
                        if sum(check) != 0:
                            # Now set everything to be the minimum of the duplicated
                            stockdata['Volume'] = stockdata.groupby(stockdata.index)['Volume'].transform('min')

                        stockdata = stockdata[~stockdata.index.duplicated(keep='first')]
                        stockdata = stockdata.sort_index()
                        stockdata.to_csv(csvdir_name+infilename, mode='w')

                    except Exception as inst:
                        print(inst)
                        print('Update failed')
                else:
                    print(f"No update needed for {stock}")

                # Wait a while to avoid data error which seems to be happening a lot for yfinance
                time.sleep(0.4)

        # When done, update the last update file to current time (UTC-5). Now trade_day instead
        lastupdate['Date'] = trade_day #(datetime.utcnow() - timedelta(hours=5)).date()
        lastupdate.to_csv(csvdir_name+"last_update.dat", mode='w', index=False)
    else:
        print("No update needed for the database!")
