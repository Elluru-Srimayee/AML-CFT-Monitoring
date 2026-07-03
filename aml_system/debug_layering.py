from pathlib import Path
import sys
sys.path.insert(0, str(Path('.')))
import pandas as pd
from datetime import datetime, timedelta
from src.rules_engine.rule_layering import LayeringRule

def make_txn_df(rows: list):
    defaults = {
        "Txn_id": 0,
        "Timestamp": datetime(2023, 1, 1),
        "Sender_account": "ACC001",
        "Receiver_account": "ACC002",
        "Amount": 1000.0,
        "Payment_currency": "USD",
        "Received_currency": "USD",
        "Sender_bank_location": "United States",
        "Receiver_bank_location": "United States",
        "Payment_type": "ACH",
        "Is_laundering": 0,
        "Laundering_type": "",
    }
    data = [{**defaults, **row, "Txn_id": i} for i, row in enumerate(rows)]
    return pd.DataFrame(data)

rows = [
    {"Sender_account":"A000","Receiver_account":"B000","Timestamp":datetime(2023,1,1)},
    {"Sender_account":"B000","Receiver_account":"C000","Timestamp":datetime(2023,1,1)+timedelta(hours=1)},
    {"Sender_account":"C000","Receiver_account":"D000","Timestamp":datetime(2023,1,1)+timedelta(hours=2)},
]

df = make_txn_df(rows)
rule = LayeringRule({"enabled":True,"window_hours":72,"min_chain_length":3,"min_fan_degree":3})
res = rule.apply(df)
print('triggered:', res.triggered_indices)
print('reasons:', res.reasons)
# Inspect adjacency maps like the rule does
from collections import defaultdict
adjacency_out = defaultdict(list)
adjacency_in = defaultdict(list)
for _, row in df.iterrows():
    sender = row['Sender_account']
    receiver = row['Receiver_account']
    ts = row['Timestamp']
    idx = row.name
    amount = row['Amount']
    adjacency_out[sender].append((receiver, ts, idx, amount))
    adjacency_in[receiver].append((sender, ts, idx, amount))

print('adj_out:', dict(adj for adj in adjacency_out.items()))
print('adj_in:', dict(adj for adj in adjacency_in.items()))
senders = set(df['Sender_account'].unique())
receivers = set(df['Receiver_account'].unique())
passthrough = senders & receivers
print('senders:', senders)
print('receivers:', receivers)
print('passthrough:', passthrough)
