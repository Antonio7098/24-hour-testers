#!/usr/bin/env python3
"""
REL-002: Race Condition Test against Patched Server (with artificial delays)

This test runs multiple iterations against the patched server to maximize
the probability of detecting the TOCTOU race condition.
"""

import asyncio
import aiohttp
import json
import time
import statistics
from datetime import datetime
from dataclasses import dataclass
import sys

BASE_URL = "http://localhost:3001"  # Patched server
AUTH_HEADERS = {"X-Fin-Token": "banker-secret"}

@dataclass
class TransferResult:
    success: bool
    from_account: int
    to_account: int
    amount: float
    duration_ms: float = 0.0
    error: str = None

async def get_accounts(session: aiohttp.ClientSession) -> dict:
    """Fetch current account balances."""
    async with session.get(f"{BASE_URL}/accounts", headers=AUTH_HEADERS) as resp:
        data = await resp.json()
        return {acc["id"]: acc for acc in data}

async def execute_transfer(session: aiohttp.ClientSession, from_acc: int, to_acc: int, amount: float, key: str) -> TransferResult:
    """Execute a single transfer request."""
    start = time.perf_counter()
    try:
        async with session.post(
            f"{BASE_URL}/transfer",
            headers={**AUTH_HEADERS, "Idempotency-Key": key},
            json={"from_account": from_acc, "to_account": to_acc, "amount": amount}
        ) as resp:
            duration_ms = (time.perf_counter() - start) * 1000
            data = await resp.json()
            return TransferResult(
                success=resp.status == 200,
                from_account=from_acc,
                to_account=to_acc,
                amount=amount,
                duration_ms=duration_ms,
                error=None if resp.status == 200 else data.get("error", f"HTTP {resp.status}")
            )
    except Exception as e:
        return TransferResult(
            success=False, from_account=from_acc, to_account=to_acc,
            amount=amount, duration_ms=0, error=str(e)
        )

async def run_iteration(iteration: int, num_transfers: int, amount: float) -> dict:
    """Run a single iteration of the race condition test."""
    # Get initial state
    async with aiohttp.ClientSession() as session:
        initial = await get_accounts(session)
    init_balance = initial[101]["balance"]
    
    # Fire concurrent transfers
    tasks = []
    async with aiohttp.ClientSession() as session:
        start = time.perf_counter()
        for i in range(num_transfers):
            key = f"iter{iteration}-transfer{i}-{start}"
            tasks.append(execute_transfer(session, 101, 102, amount, key))
        await asyncio.sleep(0.01)
        results = await asyncio.gather(*tasks)
    
    # Get final state
    async with aiohttp.ClientSession() as session:
        final = await get_accounts(session)
    
    final_balance = final[101]["balance"]
    successful = sum(1 for r in results if r.success)
    total_transferred = sum(r.amount for r in results if r.success)
    
    # Check for race condition
    race_detected = final_balance < 0
    expected_final = init_balance - (successful * amount)
    balance_discrepancy = final_balance - expected_final
    
    return {
        "iteration": iteration,
        "initial_balance": init_balance,
        "final_balance": final_balance,
        "expected_final": expected_final,
        "successful": successful,
        "total_transferred": total_transferred,
        "race_detected": race_detected,
        "balance_discrepancy": balance_discrepancy,
        "duration_ms": (time.perf_counter() - start) * 1000
    }

async def main():
    print("=" * 70)
    print("REL-002: Race Condition Test against Patched Server")
    print("Server has artificial delays to expose TOCTOU vulnerability")
    print("=" * 70)
    
    num_iterations = 20
    transfers_per_iteration = 5
    transfer_amount = 1200  # With $5000 balance, expect 4 successful, 1 fail
    
    print(f"\nConfiguration:")
    print(f"  Iterations: {num_iterations}")
    print(f"  Transfers per iteration: {transfers_per_iteration}")
    print(f"  Amount per transfer: ${transfer_amount}")
    print(f"  Expected per iteration: 4 success, 1 fail")
    
    results = []
    race_count = 0
    discrepancy_count = 0
    
    for i in range(num_iterations):
        result = await run_iteration(i + 1, transfers_per_iteration, transfer_amount)
        results.append(result)
        
        if result["race_detected"]:
            race_count += 1
            print(f"\n[!] ITERATION {i+1}: RACE CONDITION DETECTED!")
            print(f"    Initial: ${result['initial_balance']}, Final: ${result['final_balance']}")
            print(f"    Overdraft: ${abs(result['final_balance']):.2f}")
        
        if abs(result["balance_discrepancy"]) > 0.01:
            discrepancy_count += 1
        
        if (i + 1) % 5 == 0:
            print(f"  Completed {i + 1}/{num_iterations} iterations...")
    
    # Summary
    races_with_overdraft = sum(1 for r in results if r["final_balance"] < 0)
    avg_discrepancy = statistics.mean(abs(r["balance_discrepancy"]) for r in results)
    
    print(f"\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\nTotal Iterations: {num_iterations}")
    print(f"Race Conditions Detected: {races_with_overdraft}")
    print(f"Balance Discrepancies: {discrepancy_count}")
    print(f"Average Discrepancy: ${avg_discrepancy:.2f}")
    
    # Final balances check
    print(f"\nFinal Account State:")
    async with aiohttp.ClientSession() as session:
        final = await get_accounts(session)
    for acc_id in [101, 102, 999]:
        print(f"  Account {acc_id}: ${final[acc_id]['balance']:,.2f}")
    
    if races_with_overdraft > 0:
        print(f"\n[!] RACE CONDITION BUG CONFIRMED!")
        print(f"    The TOCTOU vulnerability was triggered {races_with_overdraft} times")
        print(f"    This demonstrates the lack of proper synchronization mechanisms")
        return {"passed": False, "races_found": races_with_overdraft}
    else:
        print(f"\n[OK] No race conditions detected in {num_iterations} iterations")
        print(f"    Note: Race conditions are probabilistic; vulnerability still exists in code")
        return {"passed": True, "races_found": 0}

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result["passed"] else 1)
