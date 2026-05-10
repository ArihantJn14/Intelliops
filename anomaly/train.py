# anomaly/train.py
from api.influx_queries import query_multi_field
from anomaly.detector import detector, FEATURES

print('[Train] Fetching historical data from InfluxDB...')
fields_data = query_multi_field(FEATURES, hours=168)

min_len = min(len(v) for v in fields_data.values())
readings = []
for i in range(min_len):
    row = {field: fields_data[field][i]['value'] for field in FEATURES}
    readings.append(row)

print(f'[Train] Got {len(readings)} data points across {len(FEATURES)} features')
result = detector.train(readings)
print(f'[Train] Done: {result}')
print('[Train] Model saved to anomaly/models/isolation_forest.pkl')