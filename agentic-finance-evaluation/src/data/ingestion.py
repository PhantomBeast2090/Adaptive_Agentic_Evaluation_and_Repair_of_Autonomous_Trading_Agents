import os
import yaml
import pandas as pd
import yfinance as yf
from pathlib import Path

def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def fetch_and_normalize_data(tickers, start_date, end_date):
    print(f"Fetching data for {tickers} from {start_date} to {end_date}...")
    data = yf.download(tickers, start=start_date, end=end_date)
    
    # Extract only the Adjusted Close prices
    if 'Adj Close' in data.columns:
        df = data['Adj Close'].copy()
    else:
        df = data['Close'].copy()
        
    if isinstance(df, pd.Series):
        df = pd.DataFrame(df, columns=[tickers[0]])
        
    print("Normalizing data (forward fill, drop missing)...")
    df = df.ffill().dropna()
    df.index = pd.to_datetime(df.index)
    return df

def split_and_save_data(df, splits_config, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    
    for split_name, dates in splits_config.items():
        start_date = pd.to_datetime(dates['start_date'])
        # yfinance often requires the end_date to be inclusive, but slicing is inclusive on both ends in pandas
        end_date = pd.to_datetime(dates['end_date'])
        
        split_df = df.loc[(df.index >= start_date) & (df.index <= end_date)].copy()
        
        output_file = Path(output_dir) / f"{split_name}.parquet"
        split_df.to_parquet(output_file)
        
        print(f"Saved {split_name} split to {output_file} ({len(split_df)} rows)")

def main():
    base_dir = Path(__file__).resolve().parent.parent.parent
    
    env_config_path = base_dir / 'configs' / 'env.yaml'
    exp_config_path = base_dir / 'configs' / 'experiment.yaml'
    
    env_config = load_config(env_config_path)
    exp_config = load_config(exp_config_path)
    
    tickers = env_config['market']['tickers']
    start_date = env_config['market']['start_date']
    end_date = env_config['market']['end_date']
    
    df = fetch_and_normalize_data(tickers, start_date, end_date)
    
    splits_config = exp_config['data_splits']
    output_dir = base_dir / 'data' / 'processed' / 'market_splits'
    
    split_and_save_data(df, splits_config, output_dir)
    print("Data ingestion and splitting completed successfully.")

if __name__ == "__main__":
    main()
