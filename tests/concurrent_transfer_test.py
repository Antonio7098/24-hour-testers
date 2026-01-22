#!/usr/bin/env python3
"""
REL-002: Concurrent Transfer Race Condition Test

Tests for TOCTOU race condition vulnerability in FinCore banking API.
Executes simultaneous transfers from same source account to multiple recipients
within 100ms window, verifies final balances match expected values.
"""

import asyncio
import aiohttp
import json
import time
import statistics
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

BASE_URL = "http://localhost:3000"
AUTH_HEADERS = {"X-Fin-Token": "banker-secret"}

@dataclass
class TransferResult:
    success: bool
    from_account: int
    to_account: int
    amount: float
    response: dict = None
    error: str = None
    duration_ms: float = 0.0

@dataclass
class TestReport:
    test_name: str
    start_time: str
    end_time: str
    initial_balances: dict
    final_balances: dict
    expected_balances: dict
    transfers: List[TransferResult] = field(default_factory=list)
    race_condition_detected: bool = False
    overdraft_amount: float = 0.0
    invariant_violations: List[str] = field(default_factory=list)
    passed: bool = False

def reset_account_balances():
    """Reset account balances to known state via direct server restart or API."""
    # In production, would use database reset. Here we note the starting state.
    return {
        101: 5000.00,  # Alice (source)
        102: 150.00,   # Bob
        999: 999999.00 # Admin
    }

async def get_accounts(session: aiohttp.ClientSession) -> Dict[int, Dict]:
    """Fetch current account balances."""
    async with session.get(f"{BASE_URL}/accounts", headers=AUTH_HEADERS) as resp:
        data = await resp.json()
        return {acc["id"]: acc for acc in data}

async def execute_transfer(session: aiohttp.ClientSession, from_acc: int, to_acc: int, amount: float, idempotency_key: str) -> TransferResult:
    """Execute a single transfer request."""
    start = time.perf_counter()
    try:
        async with session.post(
            f"{BASE_URL}/transfer",
            headers={**AUTH_HEADERS, "Idempotency-Key": idempotency_key},
            json={
                "from_account": from_acc,
                "to_account": to_acc,
                "amount": amount
            }
        ) as resp:
            duration_ms = (time.perf_counter() - start) * 1000
            data = await resp.json()
            
            result = TransferResult(
                success=resp.status == 200,
                from_account=from_acc,
                to_account=to_acc,
                amount=amount,
                response=data,
                duration_ms=duration_ms
            )
            
            if not result.success:
                result.error = data.get("error", f"HTTP {resp.status}")
                
            return result
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        return TransferResult(
            success=False,
            from_account=from_acc,
            to_account=to_acc,
            amount=amount,
            error=str(e),
            duration_ms=duration_ms
        )

async def concurrent_transfer_test():
    """
    Execute concurrent transfers from Alice (101) to test race condition.
    
    Scenario: Alice has 5000. We execute 5 transfers of 1200 each.
    Expected: Only 4 should succeed (5000/1200 = 4 with remainder)
    Bug: All 5 may succeed due to TOCTOU race condition, causing negative balance.
    """
    print("=" * 70)
    print("REL-002: Concurrent Transfer Race Condition Test")
    print("=" * 70)
    
    # Record initial state
    async with aiohttp.ClientSession() as session:
        initial_accounts = await get_accounts(session)
    
    initial_balances = {k: v["balance"] for k, v in initial_accounts.items()}
    source_account = 101  # Alice
    transfer_amount = 1200.00
    num_transfers = 5  # 5 * 1200 = 6000, but Alice only has 5000
    recipients = [102, 999, 102, 999, 102]  # Mix of Bob and Admin
    
    print(f"\nInitial State:")
    for acc_id, balance in initial_balances.items():
        print(f"  Account {acc_id}: ${balance:,.2f}")
    
    print(f"\nTest Configuration:")
    print(f"  Source Account: {source_account} (Alice)")
    print(f"  Transfer Amount: ${transfer_amount:,.2f}")
    print(f"  Number of Transfers: {num_transfers}")
    print(f"  Total Requested: ${transfer_amount * num_transfers:,.2f}")
    print(f"  Available Balance: ${initial_balances[source_account]:,.2f}")
    print(f"  Expected Successful: {int(initial_balances[source_account] // transfer_amount)}")
    print(f"  Expected Final Balance: ${initial_balances[source_account] % transfer_amount:,.2f}")
    
    # Execute concurrent transfers
    print(f"\nExecuting {num_transfers} concurrent transfers within 100ms window...")
    start_time = time.perf_counter()
    
    tasks = []
    async with aiohttp.ClientSession() as session:
        for i in range(num_transfers):
            idempotency_key = f"race-test-{start_time}-{i}"
            task = execute_transfer(
                session,
                source_account,
                recipients[i],
                transfer_amount,
                idempotency_key
            )
            tasks.append(task)
        
        # Fire all requests as close together as possible
        await asyncio.sleep(0.01)  # Brief sync pause
        results = await asyncio.gather(*tasks)
    
    end_time = time.perf_counter()
    total_duration_ms = (end_time - start_time) * 1000
    
    # Record final state
    async with aiohttp.ClientSession() as session:
        final_accounts = await get_accounts(session)
    
    final_balances = {k: v["balance"] for k, v in final_accounts.items()}
    
    # Analyze results
    print(f"\nTransfer Results:")
    successful = 0
    failed = 0
    for i, result in enumerate(results):
        status = "SUCCESS" if result.success else f"FAILED ({result.error})"
        print(f"  [{i+1}] -> Account {result.to_account}: {status} ({result.duration_ms:.2f}ms)")
        if result.success:
            successful += 1
        else:
            failed += 1
    
    # Verify invariants
    invariant_violations = []
    race_detected = False
    overdraft_amount = 0.0
    
    # Check 1: Final balance should not be negative
    final_source_balance = final_balances[source_account]
    if final_source_balance < 0:
        race_detected = True
        overdraft_amount = abs(final_source_balance)
        invariant_violations.append(
            f"OVERDRAFT: Source account balance is ${final_source_balance:,.2f} (negative!)"
        )
    
    # Check 2: Sum of transfers should not exceed initial balance
    total_transferred = sum(r.amount for r in results if r.success) * -1  # Debit is negative
    expected_max_debit = initial_balances[source_account]
    
    if final_source_balance < 0:
        # Bug confirmed: balance went negative
        invariant_violations.append(
            f"DOUBLE-SPENDING: ${total_transferred:,.2f} transferred but only ${expected_max_debit:,.2f} available"
        )
    
    # Check 3: Final balance should match expected (initial - successful transfers)
    expected_final = initial_balances[source_account] - (successful * transfer_amount)
    balance_discrepancy = final_source_balance - expected_final
    
    if abs(balance_discrepancy) > 0.01:
        invariant_violations.append(
            f"BALANCE DISCREPANCY: Expected ${expected_final:,.2f}, got ${final_source_balance:,.2f} "
            f"(diff: ${balance_discrepancy:,.2f})"
        )
    
    # Check 4: Recipients should receive correct amounts
    for acc_id in [102, 999]:
        expected_credit = sum(
            r.amount for r in results 
            if r.success and r.to_account == acc_id
        )
        actual_credit = final_balances[acc_id] - initial_balances[acc_id]
        if abs(expected_credit - actual_credit) > 0.01:
            invariant_violations.append(
                f"CREDIT MISMATCH: Account {acc_id} expected +${expected_credit:,.2f}, "
                f"actual change +${actual_credit:,.2f}"
            )
    
    # Determine test pass/fail
    test_passed = (
        not race_detected and
        final_source_balance >= 0 and
        len(invariant_violations) == 0
    )
    
    print(f"\n" + "=" * 70)
    print("ANALYSIS RESULTS")
    print("=" * 70)
    print(f"\nTiming:")
    print(f"  Total Execution Time: {total_duration_ms:.2f}ms")
    print(f"  Average Transfer Time: {statistics.mean(r.duration_ms for r in results):.2f}ms")
    
    print(f"\nBalances:")
    print(f"  Initial (Alice): ${initial_balances[source_account]:,.2f}")
    print(f"  Final (Alice):   ${final_source_balance:,.2f}")
    print(f"  Expected Final:  ${expected_final:,.2f}")
    
    print(f"\nStatistics:")
    print(f"  Successful Transfers: {successful}")
    print(f"  Failed Transfers: {failed}")
    print(f"  Total Transferred: ${sum(r.amount for r in results if r.success):,.2f}")
    
    if invariant_violations:
        print(f"\n[!] INVARIANT VIOLATIONS DETECTED:")
        for violation in invariant_violations:
            print(f"  - {violation}")
    else:
        print(f"\n[OK] All invariants maintained")
    
    if race_detected:
        print(f"\n[!] RACE CONDITION BUG CONFIRMED!")
        print(f"   Overdraft Amount: ${overdraft_amount:,.2f}")
        print(f"   Vulnerability: TOCTOU (Time-of-Check to Time-of-Use)")
        print(f"   Impact: Funds double-spent due to non-atomic balance operations")
    else:
        print(f"\n[OK] No race condition detected")
        print(f"   Final balance is non-negative and matches expected value")
    
    # Generate report
    report = TestReport(
        test_name="REL-002 Concurrent Transfer Race Condition",
        start_time=datetime.fromtimestamp(start_time).isoformat(),
        end_time=datetime.fromtimestamp(end_time).isoformat(),
        initial_balances=initial_balances,
        final_balances=final_balances,
        expected_balances={source_account: expected_final},
        transfers=results,
        race_condition_detected=race_detected,
        overdraft_amount=overdraft_amount,
        invariant_violations=invariant_violations,
        passed=test_passed
    )
    
    # Save report
    report_data = {
        "test_name": report.test_name,
        "start_time": report.start_time,
        "end_time": report.end_time,
        "initial_balances": report.initial_balances,
        "final_balances": report.final_balances,
        "expected_balances": report.expected_balances,
        "transfers": [
            {
                "success": r.success,
                "from_account": r.from_account,
                "to_account": r.to_account,
                "amount": r.amount,
                "duration_ms": r.duration_ms,
                "error": r.error
            }
            for r in report.transfers
        ],
        "race_condition_detected": report.race_condition_detected,
        "overdraft_amount": report.overdraft_amount,
        "invariant_violations": report.invariant_violations,
        "passed": report.passed
    }
    
    report_file = f"runs/REL-002/race_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    import os
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    
    with open(report_file, 'w') as f:
        json.dump(report_data, f, indent=2)
    
    print(f"\n[REPORT] Report saved to: {report_file}")
    print("=" * 70)
    
    return report

if __name__ == "__main__":
    asyncio.run(concurrent_transfer_test())
