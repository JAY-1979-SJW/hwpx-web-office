#!/usr/bin/env python3
"""
Client API integration smoke test for HWPX parser.
Verifies that the HWPX parser engine can be called via HTTP API.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any
import urllib.request
import urllib.error


class HwpxSmokeTest:
    def __init__(self, base_url: str, sample_path: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.sample_path = Path(sample_path)
        self.timeout = timeout
        self.result = {
            'sample': str(self.sample_path),
            'base_url': self.base_url,
            'timestamp': time.time(),
            'health_ok': False,
            'parse_ok': False,
            'error': None,
            'error_type': None,
            'response': None,
            'validation': {},
        }

    def health_check(self) -> bool:
        """Check if engine is running."""
        try:
            url = f"{self.base_url}/health"
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                if response.status == 200:
                    self.result['health_ok'] = True
                    return True
                else:
                    self.result['error'] = f"Health check returned {response.status}"
                    self.result['error_type'] = 'HEALTH_FAIL'
                    return False
        except urllib.error.URLError as e:
            self.result['error'] = f"Engine not running: {e}"
            self.result['error_type'] = 'ENGINE_NOT_RUNNING'
            return False
        except Exception as e:
            self.result['error'] = f"Health check timeout/error: {e}"
            self.result['error_type'] = 'TIMEOUT'
            return False

    def parse_hwpx(self) -> bool:
        """Call /parse-hwpx endpoint."""
        if not self.sample_path.exists():
            self.result['error'] = f"Sample file not found: {self.sample_path}"
            self.result['error_type'] = 'FILE_NOT_FOUND'
            return False

        try:
            with open(self.sample_path, 'rb') as f:
                sample_data = f.read()

            url = f"{self.base_url}/parse-hwpx"
            req = urllib.request.Request(
                url,
                data=sample_data,
                headers={'Content-Type': 'application/octet-stream'},
                method='POST',
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status != 200:
                    self.result['error'] = f"Parse request returned {response.status}"
                    self.result['error_type'] = 'PARSE_HTTP_FAIL'
                    return False

                response_data = response.read().decode('utf-8')
                self.result['response'] = json.loads(response_data)
                self.result['parse_ok'] = True

                # Validate response schema
                self._validate_response()
                return True

        except urllib.error.HTTPError as e:
            self.result['error'] = f"Parse request HTTP error: {e.code} {e.reason}"
            self.result['error_type'] = 'PARSE_HTTP_FAIL'
            return False
        except urllib.error.URLError as e:
            self.result['error'] = f"Parse request URL error: {e}"
            self.result['error_type'] = 'ENGINE_NOT_RUNNING'
            return False
        except json.JSONDecodeError as e:
            self.result['error'] = f"Invalid JSON response: {e}"
            self.result['error_type'] = 'PARSE_HTTP_FAIL'
            return False
        except Exception as e:
            self.result['error'] = f"Parse request error: {e}"
            self.result['error_type'] = 'TIMEOUT'
            return False

    def _validate_response(self) -> None:
        """Validate response schema."""
        required_keys = [
            'ok', 'schemaVersion', 'engineVersion', 'requestId',
            'inputFileType', 'fullText', 'paragraphs', 'blocks',
            'tables', 'warnings', 'errors'
        ]

        resp = self.result['response']
        validation = self.result['validation']

        for key in required_keys:
            if key in resp:
                validation[key] = 'PRESENT'
            else:
                validation[key] = 'MISSING'
                self.result['error_type'] = 'CONTRACT_KEY_MISSING'
                self.result['error'] = f"Missing required key: {key}"

        if resp.get('ok') is False:
            self.result['error_type'] = 'OK_FALSE'
            self.result['error'] = "Response ok=false"

        if resp.get('fullText') == '':
            self.result['error_type'] = 'EMPTY_TEXT'
            self.result['error'] = "Response fullText is empty"

        # Store metrics
        if 'fullText' in resp:
            validation['fullText_length'] = len(resp['fullText'])
        if 'paragraphs' in resp:
            validation['paragraphs_count'] = len(resp['paragraphs'])
        if 'blocks' in resp:
            validation['blocks_count'] = len(resp['blocks'])
        if 'tables' in resp:
            validation['tables_count'] = len(resp['tables'])

    def run(self) -> bool:
        """Run smoke test."""
        print(f"\n=== HWPX Client Smoke Test ===")
        print(f"Base URL: {self.base_url}")
        print(f"Sample:   {self.sample_path}")

        # Step 1: Health check
        print("\n[1/2] Health check...")
        if not self.health_check():
            print(f"  ✗ FAIL: {self.result['error']}")
            return False
        print("  ✓ PASS")

        # Step 2: Parse HWPX
        print("\n[2/2] Parse HWPX...")
        if not self.parse_hwpx():
            print(f"  ✗ FAIL: {self.result['error']}")
            return False
        print("  ✓ PASS")

        # Validate schema
        print("\n=== Response Validation ===")
        for key, status in self.result['validation'].items():
            if status == 'PRESENT':
                print(f"  ✓ {key}")
            elif status == 'MISSING':
                print(f"  ✗ {key}: MISSING")
            else:
                print(f"  • {key}: {status}")

        resp = self.result['response']
        print(f"\n=== Response Summary ===")
        print(f"  Schema Version: {resp.get('schemaVersion')}")
        print(f"  Engine Version: {resp.get('engineVersion')}")
        print(f"  Full Text Length: {self.result['validation'].get('fullText_length', 0)}")
        print(f"  Paragraphs: {self.result['validation'].get('paragraphs_count', 0)}")
        print(f"  Blocks: {self.result['validation'].get('blocks_count', 0)}")
        print(f"  Tables: {self.result['validation'].get('tables_count', 0)}")
        print(f"  Warnings: {len(resp.get('warnings', []))}")
        print(f"  Errors: {len(resp.get('errors', []))}")

        if resp.get('errors'):
            print(f"\n  Errors in response:")
            for err in resp['errors'][:3]:  # Show first 3
                print(f"    - {err}")

        return True

    def to_json(self) -> str:
        """Export result as JSON."""
        return json.dumps(self.result, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(
        description='HWPX parser client API smoke test'
    )
    parser.add_argument(
        '--base-url',
        default='http://127.0.0.1:8080',
        help='Base URL of the HWPX parser engine (default: http://127.0.0.1:8080)'
    )
    parser.add_argument(
        '--sample',
        required=True,
        help='Path to HWPX sample file'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Request timeout in seconds (default: 30)'
    )
    parser.add_argument(
        '--json-output',
        help='Output JSON result to file'
    )

    args = parser.parse_args()

    test = HwpxSmokeTest(args.base_url, args.sample, args.timeout)
    success = test.run()

    if args.json_output:
        with open(args.json_output, 'w') as f:
            f.write(test.to_json())
        print(f"\nJSON output: {args.json_output}")

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
