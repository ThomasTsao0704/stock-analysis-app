
import os
import requests
import pandas as pd
from datetime import datetime

def fetch_twse_stock_data(stock_no: str, year: int, month: int) -> pd.DataFrame:
    url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
    date_str = f"{year}{month:02d}01"
    params = {
        "response": "json",
        "date": date_str,
        "stockNo": stock_no
    }
    r = requests.get(url, params=params)
    if r.status_code != 200:
        return pd.DataFrame()

    json_data = r.json()
    if json_data.get("stat") != "OK":
        return pd.DataFrame()

    df = pd.DataFrame(json_data["data"], columns=json_data["fields"])
    df["日期"] = pd.to_datetime(df["日期"].str.replace("/", "-"))
    df["收盤價"] = pd.to_numeric(df["收盤價"].str.replace(",", ""), errors="coerce")
    return df[["日期", "收盤價"]]
