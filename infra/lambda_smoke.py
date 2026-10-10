"""Verify API Gateway v2 events through local RIE, including response-envelope limits."""
import base64
import gzip
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

RUN = 'analysis-1616d67b7b28fb2442d9747f'
RIE = 'http://127.0.0.1:9000/2015-03-31/functions/function/invocations'
DIRECT = 'http://127.0.0.1:8002'


def invoke(path, encoding='gzip'):
    headers = {'host': 'example.execute-api.ap-southeast-2.amazonaws.com', 'origin': 'http://localhost:8443'}
    if encoding:
        headers['accept-encoding'] = encoding
    event = {'version': '2.0', 'routeKey': '$default', 'rawPath': path, 'rawQueryString': '',
             'headers': headers, 'isBase64Encoded': False,
             'requestContext': {'accountId': 'local', 'apiId': 'local', 'domainName': headers['host'],
                                'domainPrefix': 'example', 'stage': '$default', 'requestId': 'local-check',
                                'timeEpoch': 0, 'http': {'method': 'GET', 'path': path,
                                  'protocol': 'HTTP/1.1', 'sourceIp': '127.0.0.1', 'userAgent': 'lambda-smoke'}}}
    start = time.monotonic()
    request = Request(RIE, data=json.dumps(event).encode(), headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=60) as response:
        raw = response.read()
    envelope = json.loads(raw)
    if envelope.get('statusCode') != 200:
        raise AssertionError(envelope)
    payload = base64.b64decode(envelope['body']) if envelope.get('isBase64Encoded') else envelope['body'].encode()
    returned_headers = {k.lower(): v for k, v in envelope.get('headers', {}).items()}
    coding = returned_headers.get('content-encoding')
    wire_bytes = len(payload)
    if coding == 'gzip':
        payload = gzip.decompress(payload)
    result = json.loads(payload)
    with urlopen(DIRECT + path, timeout=30) as response:
        expected = json.load(response)
    assert result == expected, f'Content changed for {path}'
    return {'path': path, 'requested_encoding': encoding, 'content_encoding': coding,
            'envelope_bytes': len(raw), 'wire_body_bytes': wire_bytes, 'decoded_bytes': len(payload),
            'within_lambda_6mib': len(raw) < 6 * 1024 * 1024,
            'content_identical': True, 'seconds': round(time.monotonic() - start, 3)}


if __name__ == '__main__':
    paths = ['/api/v1/health', '/api/v1/runs/demo-yamuna-2023/summary']
    paths += [f'/api/v1/runs/{RUN}/{layer}' for layer in ('summary', 'localities', 'evacuation', 'safe-sites', 'flood', 'road-impacts')]
    report = []
    for path in paths:
        row = invoke(path)
        report.append(row)
        print(json.dumps(row), flush=True)
    row = invoke(f'/api/v1/runs/{RUN}/road-impacts', None)
    report.append(row)
    print(json.dumps(row), flush=True)
    Path('artifacts/deployment/lambda-response-check.json').write_text(json.dumps(report, indent=2) + '\n')
    if not all(item['within_lambda_6mib'] for item in report):
        sys.exit('At least one response exceeds the Lambda buffered limit; review before deployment.')
