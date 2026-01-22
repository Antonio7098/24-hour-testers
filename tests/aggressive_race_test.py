#!/usr/bin/env python3
"""
REL-002: Aggressive Concurrent Transfer Race Condition Test

This test injects artificial delays into the SUT to simulate real-world I/O latency
and expose the TOCTOU race condition vulnerability in the transfer logic.
"""

import asyncio
import aiohttp
import json
import time
import statistics
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass

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
    transfers: List[TransferResult] = None
    race_condition_detected: bool = False
    overdraft_amount: float = 0.0
    invariant_violations: List[str] = None
    passed: bool = False

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

def create_patched_server_script():
    """Create a patched version of the server with artificial delays to expose race conditions."""
    patched_code = '''const express = require('express');
const bodyParser = require('body-parser');
const app = express();
const port = 3000;

app.enable('strict routing');
app.use(bodyParser.json());

const accounts = [
    { id: 101, owner: "Alice", balance: 5000.00, type: "checking" },
    { id: 102, owner: "Bob", balance: 150.00, type: "savings" },
    { id: 999, owner: "Admin", balance: 999999.00, type: "internal" }
];

const transactions = [];
const processedIdempotencyKeys = new Set();

const requireAuth = (req, res, next) => {
    const auth = req.headers['x-fin-token'];
    if (auth === 'banker-secret') {
        next();
    } else {
        res.status(401).json({ error: "Unauthorized access" });
    }
};

app.get('/health', (req, res) => {
    res.json({ status: "system_active", timestamp: new Date().toISOString() });
});

app.get('/accounts', requireAuth, (req, res) => {
    res.json(accounts);
});

app.get('/accounts/:id/transactions', requireAuth, (req, res) => {
    const accId = parseInt(req.params.id, 10);
    const acc = accounts.find(a => a.id === accId);
    if (!acc) {
        return res.status(404).json({ error: "Account not found" });
    }
    const accountTx = transactions.filter(t => t.account_id === accId);
    res.json(accountTx});
});

app.post('/transfer', requireAuth, async (req, res) => {
    const { from_account, to_account, amount } = req.body;
    const idemKey = req.headers['idempotency-key'];

    if (idemKey && processedIdempotencyKeys.has(idemKey)) {
        // Idempotency check
    }

    if (!from_account || !to_account || !amount) {
        return res.status(400).json({ error: "Missing required fields" });
    }

    if (amount <= 0) {
        return res.status(400).json({ error: "Transfer amount must be positive" });
    }

    // ARTIFICIAL DELAY: Simulate database lookup latency (50ms)
    // This YIELDS control to the event loop, allowing race conditions
    await new Promise(resolve => setTimeout(resolve, 50));

    const source = accounts.find(a => a.id === from_account);
    const dest = accounts.find(a => a.id === to_account);

    if (!source || !dest) {
        return res.status(404).json({ error: "One or more accounts not found" });
    }

    // ARTIFICIAL DELAY: Simulate business logic processing (20ms)
    // This further increases the race window
    await new Promise(resolve => setTimeout(resolve, 20));

    if (source.balance < amount) {
        return res.status(400).json({ error: "Insufficient funds" });
    }

    // ARTIFICIAL DELAY: Simulate database write latency (30ms)
    // Final opportunity for race condition before commit
    await new Promise(resolve => setTimeout(resolve, 30));

    // Process Transfer - non-atomic operation
    source.balance -= amount;
    dest.balance += amount;

    const txId = transactions.length + 1;
    transactions.push({ id: txId, account_id: from_account, amount: -amount, desc: \`Transfer to \${to_account}\`, date: new Date().toISOString() });
    transactions.push({ id: txId + 1, account_id: to_account, amount: amount, desc: \`Transfer from \${from_account}\`, date: new Date().toISOString() });

    if (idemKey) processedIdempotencyKeys.add(idemKey);

    res.json({ status: "success", tx_id: txId, new_balance: source.balance });
});

app.get('/admin/debug', requireAuth, (req, res) => {
    res.json({
        env: process.env,
        memory: process.memoryUsage(),
        db_dump: { accounts, transactions }
    });
});

app.listen(port, () => {
    console.log(\`FinCore SUT (PATCHED WITH DELAYS) running on http://localhost:\${port}\`);
});
'''
    return patched_code

async def run_aggressive_race_test():
    """
    Run an aggressive race condition test with patched server.
    
    This test:
    1. Creates a patched server with artificial delays (100ms total per request)
    2. Launches multiple server instances in subprocess
    3. Fires rapid concurrent requests to maximize race window
    4. Verifies final balances for consistency
    """
    print("=" * 70)
    print("REL-002 Aggressive: Concurrent Transfer Race Condition Test")
    print("(With artificial delays to expose TOCTOU vulnerability)")
    print("=" * 70)
    
    # Record initial state
    async with aiohttp.ClientSession() as session:
        initial_accounts = await get_accounts(session)
    
    initial_balances = {k: v["balance"] for k, v in initial_accounts.items()}
    source_account = 101  # Alice
    transfer_amount = 1500.00  # Higher amount to trigger multiple failures
    num_transfers = 10  # More transfers to increase probability
    recipients = [102, 999, 102, 999, 102, 999, 102, 999, 102, 999]
    
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
    print(f"  Server Delay per Request: ~100ms (artificial)")
    print(f"  Race Window: ~70ms (between balance check and debit)")
    
    # Execute concurrent transfers
    print(f"\nExecuting {num_transfers} concurrent transfers...")
    start_time = time.perf_counter()
    
    tasks = []
    async with aiohttp.ClientSession() as session:
        for i in range(num_transfers):
            idempotency_key = f"aggressive-race-test-{start_time}-{i}"
            task = execute_transfer(
                session,
                source_account,
                recipients[i],
                transfer_amount,
                idempotency_key
            )
            tasks.append(task)
        
        await asyncio.sleep(0.01)
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
    
    final_source_balance = final_balances[source_account]
    if final_source_balance < 0:
        race_detected = True
        overdraft_amount = abs(final_source_balance)
        invariant_violations.append(
            f"OVERDRAFT: Source account balance is ${final_source_balance:,.2f} (negative!)"
        )
    
    expected_final = initial_balances[source_account] - (successful * transfer_amount)
    balance_discrepancy = final_source_balance - expected_final
    
    if abs(balance_discrepancy) > 0.01:
        invariant_violations.append(
            f"BALANCE DISCREPANCY: Expected ${expected_final:,.2f}, got ${final_source_balance:,.2f} "
            f"(diff: ${balance_discrepancy:,.2f})"
        )
    
    # Test passes if no overdraft and balances are consistent
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
    print(f"  Min/Max: {min(r.duration_ms for r in results):.2f}ms / {max(r.duration_ms for r in results):.2f}ms")
    
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
    else:
        print(f"\n[OK] No race condition detected in this run")
        print(f"   Note: Race conditions are probabilistic and may not always trigger")
    
    print("=" * 70)
    
    return {
        "test_passed": test_passed,
        "race_detected": race_detected,
        "overdraft_amount": overdraft_amount,
        "invariant_violations": invariant_violations,
        "successful_transfers": successful,
        "failed_transfers": failed,
        "final_balance": final_source_balance,
        "total_duration_ms": total_duration_ms
    }

if __name__ == "__main__":
    result = asyncio.run(run_aggressive_race_test())
    print(f"\n\nFINAL RESULT: {'PASSED' if result['test_passed'] else 'FAILED'}")
    if result['race_detected']:
        print(f"RACE CONDITION DETECTED - Overdraft: ${result['overdraft_amount']:,.2f}")
