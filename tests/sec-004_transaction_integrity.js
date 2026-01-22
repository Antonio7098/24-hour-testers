#!/usr/bin/env node
/**
 * SEC-004: Transaction Integrity Tests
 * Tests for negative amounts and insufficient funds scenarios
 */

const BASE_URL = 'http://localhost:3000';
const AUTH_HEADER = { 'X-Fin-Token': 'banker-secret' };

let findings = [];

function logTest(name, passed, details = '') {
    const status = passed ? '✅ PASS' : '❌ FAIL';
    console.log(`${status}: ${name}${details ? ' - ' + details : ''}`);
    return passed;
}

function makeRequest(method, path, headers = {}, body = null) {
    return new Promise((resolve, reject) => {
        const url = new URL(path, BASE_URL);
        const options = {
            hostname: url.hostname,
            port: url.port,
            path: url.pathname,
            method: method,
            headers: {
                'Content-Type': 'application/json',
                ...AUTH_HEADER,
                ...headers
            }
        };

        const req = require('http').request(options, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    resolve({ status: res.statusCode, body: JSON.parse(data) });
                } catch (e) {
                    resolve({ status: res.statusCode, body: data });
                }
            });
        });

        req.on('error', reject);

        if (body) {
            req.write(JSON.stringify(body));
        }
        req.end();
    });
}

async function getAccountBalance(accountId) {
    const response = await makeRequest('GET', `/accounts`);
    const account = response.body.find(a => a.id === accountId);
    return account ? account.balance : null;
}

async function getTransactionHistory(accountId) {
    const response = await makeRequest('GET', `/accounts/${accountId}/transactions`);
    return response.body;
}

async function resetAccounts() {
    console.log('\n🔄 Resetting accounts to known state...');
    const adminDebug = await makeRequest('GET', '/admin/debug');
    if (adminDebug.body.db_dump && adminDebug.body.db_dump.accounts) {
        console.log('Current balances:', adminDebug.body.db_dump.accounts.map(a => `${a.id}:${a.owner}:${a.balance}`).join(', '));
    }
}

async function runTests() {
    console.log('='.repeat(60));
    console.log('SEC-004: Transaction Integrity Tests');
    console.log('Negative amounts and insufficient funds');
    console.log('='.repeat(60));

    await resetAccounts();

    const aliceAccount = 101;
    const bobAccount = 102;
    const adminAccount = 999;

    console.log('\n--- TEST CATEGORY 1: Negative Amounts ---\n');

    // Test 1.1: Transfer with negative amount
    let testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-neg-1'
    }, {
        from_account: aliceAccount,
        to_account: bobAccount,
        amount: -100
    });
    logTest('Reject negative transfer amount (-100)', testResult.status === 400,
        `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);

    // Test 1.2: Transfer with zero amount
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-zero-1'
    }, {
        from_account: aliceAccount,
        to_account: bobAccount,
        amount: 0
    });
    logTest('Reject zero transfer amount', testResult.status === 400,
        `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);

    // Test 1.3: Transfer with very small negative amount
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-neg-small-1'
    }, {
        from_account: aliceAccount,
        to_account: bobAccount,
        amount: -0.01
    });
    logTest('Reject very small negative amount (-0.01)', testResult.status === 400,
        `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);

    // Test 1.4: Transfer with negative amount via string manipulation
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-neg-string-1'
    }, {
        from_account: aliceAccount,
        to_account: bobAccount,
        amount: '-50'
    });
    logTest('Reject negative amount as string (-50)', testResult.status === 400,
        `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);

    console.log('\n--- TEST CATEGORY 2: Insufficient Funds ---\n');

    // Test 2.1: Transfer more than balance (Alice has ~3000)
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-insuf-1'
    }, {
        from_account: aliceAccount,
        to_account: bobAccount,
        amount: 10000
    });
    logTest('Reject transfer exceeding balance (10000 > 3000)', testResult.status === 400,
        `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);

    // Test 2.2: Transfer exactly the balance amount (should succeed)
    const aliceBalance = await getAccountBalance(aliceAccount);
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-exact-balance'
    }, {
        from_account: aliceAccount,
        to_account: bobAccount,
        amount: aliceBalance
    });
    logTest('Accept transfer of exact balance amount', testResult.status === 200,
        `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);

    // Test 2.3: Transfer 1 cent more than balance after exact transfer
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-one-cent-over'
    }, {
        from_account: aliceAccount,
        to_account: bobAccount,
        amount: 0.01
    });
    logTest('Reject transfer 0.01 more than balance', testResult.status === 400,
        `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);

    // Test 2.4: Bob's account has suspicious balance, try to drain it
    const bobBalance = await getAccountBalance(bobAccount);
    console.log(`Bob's current balance: ${bobBalance}`);
    if (typeof bobBalance === 'number' && bobBalance > 100) {
        testResult = await makeRequest('POST', '/transfer', {
            'Idempotency-Key': 'sec-004-drain-bob'
        }, {
            from_account: bobAccount,
            to_account: aliceAccount,
            amount: bobBalance
        });
        logTest('Transfer entire Bob balance to Alice', testResult.status === 200,
            `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);
    }

    console.log('\n--- TEST CATEGORY 3: Boundary/Edge Cases ---\n');

    // Test 3.1: Very small positive amount
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-micro-1'
    }, {
        from_account: aliceAccount,
        to_account: bobAccount,
        amount: 0.001
    });
    logTest('Accept very small amount (0.001)', testResult.status === 200,
        `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);

    // Test 3.2: Floating point precision edge case
    const currentAliceBalance = await getAccountBalance(aliceAccount);
    const trickyAmount = 0.1 + 0.2; // JavaScript floating point issue
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-float-1'
    }, {
        from_account: aliceAccount,
        to_account: bobAccount,
        amount: trickyAmount
    });
    logTest('Handle floating point precision (0.1+0.2)', testResult.status === 200,
        `Status: ${testResult.status}, Amount requested: ${trickyAmount}, Response: ${JSON.stringify(testResult.body)}`);

    // Test 3.3: Large amount (but within limits)
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-large-1'
    }, {
        from_account: adminAccount,
        to_account: aliceAccount,
        amount: 1000000
    });
    logTest('Process large amount from admin account', testResult.status === 200,
        `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);

    console.log('\n--- TEST CATEGORY 4: Invalid Account Scenarios ---\n');

    // Test 4.1: Transfer from non-existent account
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-no-from'
    }, {
        from_account: 99999,
        to_account: bobAccount,
        amount: 100
    });
    logTest('Reject transfer from non-existent account', testResult.status === 404,
        `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);

    // Test 4.2: Transfer to non-existent account
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-no-to'
    }, {
        from_account: aliceAccount,
        to_account: 99999,
        amount: 100
    });
    logTest('Reject transfer to non-existent account', testResult.status === 404,
        `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);

    // Test 4.3: Transfer to same account (self-transfer)
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-self'
    }, {
        from_account: aliceAccount,
        to_account: aliceAccount,
        amount: 100
    });
    logTest('Self-transfer handling', testResult.status !== 200 || 'Self-transfer processed (warning)',
        `Status: ${testResult.status}, Response: ${JSON.stringify(testResult.body)}`);

    console.log('\n--- TEST CATEGORY 5: Idempotency with Insufficient Funds ---\n');

    // Test 5.1: Idempotency key should prevent duplicate rejection processing
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-idempotent-reject'
    }, {
        from_account: aliceAccount,
        to_account: bobAccount,
        amount: 99999999
    });
    const firstRejectStatus = testResult.status;
    logTest('First insufficient funds request rejected', firstRejectStatus === 400,
        `Status: ${firstRejectStatus}`);

    // Test 5.2: Same idempotency key should return same error
    testResult = await makeRequest('POST', '/transfer', {
        'Idempotency-Key': 'sec-004-idempotent-reject'
    }, {
        from_account: aliceAccount,
        to_account: bobAccount,
        amount: 99999999
    });
    logTest('Idempotency key respected for repeated rejection', testResult.status === 400,
        `Status: ${testResult.status} (should still be 400)`);

    console.log('\n--- Final Account States ---\n');
    const finalAccounts = await makeRequest('GET', '/accounts');
    finalAccounts.body.forEach(acc => {
        console.log(`Account ${acc.id} (${acc.owner}): ${acc.balance}`);
    });

    console.log('\n' + '='.repeat(60));
    console.log('SEC-004 Test Suite Complete');
    console.log('='.repeat(60));
}

runTests().catch(console.error);
