const express = require('express');
const app = express();
const port = 3001;

app.enable('strict routing');
app.use(express.json());

// In-memory database
const accounts = [
    { id: 101, owner: "Alice", balance: 5000.00, type: "checking", status: "active" },
    { id: 102, owner: "Bob", balance: 150.00, type: "savings", status: "active" },
    { id: 999, owner: "Admin", balance: 999999.00, type: "internal", status: "active" }
];

const transactions = [];

const processedIdempotencyKeys = new Set();

// Configurable test parameters
let transferDelayMs = 0;
let freezeDuringTransfer = false;

// Middleware for Authentication
const requireAuth = (req, res, next) => {
    const auth = req.headers['x-fin-token'];
    if (auth === 'banker-secret') {
        next();
    } else {
        res.status(401).json({ error: "Unauthorized access" });
    }
};

// 1. Health check
app.get('/health', (req, res) => {
    res.json({ status: "system_active", timestamp: new Date().toISOString() });
});

// 2. List Accounts
app.get('/accounts', requireAuth, (req, res) => {
    res.json(accounts);
});

// 3. Get Transactions
app.get('/accounts/:id/transactions', requireAuth, (req, res) => {
    const accId = parseInt(req.params.id, 10);
    const acc = accounts.find(a => a.id === accId);
    if (!acc) {
        return res.status(404).json({ error: "Account not found" });
    }
    const accountTx = transactions.filter(t => t.account_id === accId);
    res.json(accountTx);
});

// 4. Transfer Funds - Modified for atomicity testing
app.post('/transfer', requireAuth, async (req, res) => {
    const { from_account, to_account, amount } = req.body;
    const idemKey = req.headers['idempotency-key'];

    if (!from_account || !to_account || !amount) {
        return res.status(400).json({ error: "Missing required fields" });
    }

    if (amount <= 0) {
        return res.status(400).json({ error: "Transfer amount must be positive" });
    }

    const source = accounts.find(a => a.id === from_account);
    const dest = accounts.find(a => a.id === to_account);

    if (!source || !dest) {
        return res.status(404).json({ error: "One or more accounts not found" });
    }

    // Check account status BEFORE any operations
    if (source.status !== 'active') {
        return res.status(403).json({ error: "Source account is not active", account_status: source.status });
    }
    if (dest.status !== 'active') {
        return res.status(403).json({ error: "Destination account is not active", account_status: dest.status });
    }

    // Check sufficient funds
    if (source.balance < amount) {
        return res.status(400).json({ error: "Insufficient funds" });
    }

    // Simulate transfer delay for mid-flight freeze testing
    if (transferDelayMs > 0) {
        await new Promise(resolve => setTimeout(resolve, transferDelayMs));
    }

    // Check if freeze happened during transfer (mid-flight)
    if (freezeDuringTransfer && source.status !== 'active') {
        return res.status(403).json({ 
            error: "Account frozen during transfer", 
            account_status: source.status,
            stage: "mid_transfer"
        });
    }

    // Process Transfer - NON-ATOMIC (this is the bug we're testing)
    const oldSourceBalance = source.balance;
    source.balance -= amount;
    
    // Simulate mid-flight check
    if (freezeDuringTransfer && source.status !== 'active') {
        // Rollback not implemented - this is the atomicity bug
        return res.status(403).json({ 
            error: "Account frozen after debit, before credit",
            account_status: source.status,
            stage: "debit_complete_credit_pending",
            intermediate_state: true
        });
    }
    
    dest.balance += amount;

    // Record Transaction
    const txId = transactions.length + 1;
    transactions.push({ id: txId, account_id: from_account, amount: -amount, desc: `Transfer to ${to_account}`, date: new Date().toISOString() });
    transactions.push({ id: txId + 1, account_id: to_account, amount: amount, desc: `Transfer from ${from_account}`, date: new Date().toISOString() });

    res.json({ 
        status: "success", 
        tx_id: txId, 
        new_balance: source.balance,
        atomic: false
    });
});

// 5. Freeze Account - Admin endpoint for testing
app.post('/admin/freeze-account', requireAuth, (req, res) => {
    const { account_id } = req.body;
    const account = accounts.find(a => a.id === account_id);
    
    if (!account) {
        return res.status(404).json({ error: "Account not found" });
    }
    
    account.status = 'frozen';
    res.json({ 
        status: "frozen", 
        account_id: account_id,
        timestamp: new Date().toISOString()
    });
});

// 6. Unfreeze Account
app.post('/admin/unfreeze-account', requireAuth, (req, res) => {
    const { account_id } = req.body;
    const account = accounts.find(a => a.id === account_id);
    
    if (!account) {
        return res.status(404).json({ error: "Account not found" });
    }
    
    account.status = 'active';
    res.json({ 
        status: "active", 
        account_id: account_id,
        timestamp: new Date().toISOString()
    });
});

// 7. Set transfer delay for testing
app.post('/test/set-delay', requireAuth, (req, res) => {
    const { ms } = req.body;
    transferDelayMs = ms || 0;
    res.json({ status: "delay_set", delay_ms: transferDelayMs });
});

// 8. Enable/disable freeze during transfer
app.post('/test/set-freeze-during', requireAuth, (req, res) => {
    const { enabled } = req.body;
    freezeDuringTransfer = enabled || false;
    res.json({ status: "set", freeze_during: freezeDuringTransfer });
});

// 9. Reset state for testing
app.post('/test/reset', requireAuth, (req, res) => {
    accounts[0] = { id: 101, owner: "Alice", balance: 5000.00, type: "checking", status: "active" };
    accounts[1] = { id: 102, owner: "Bob", balance: 150.00, type: "savings", status: "active" };
    accounts[2] = { id: 999, owner: "Admin", balance: 999999.00, type: "internal", status: "active" };
    transactions.length = 0;
    transferDelayMs = 0;
    freezeDuringTransfer = false;
    res.json({ status: "reset" });
});

// 10. Get account state
app.get('/admin/account/:id', requireAuth, (req, res) => {
    const accId = parseInt(req.params.id, 10);
    const account = accounts.find(a => a.id === accId);
    if (!account) {
        return res.status(404).json({ error: "Account not found" });
    }
    res.json(account);
});

// 11. Admin Debug
app.get('/admin/debug', requireAuth, (req, res) => {
    res.json({
        env: process.env,
        memory: process.memoryUsage(),
        db_dump: { accounts, transactions }
    });
});

// 12. Utils echo
app.get('/utils/echo', (req, res) => {
    const msg = req.query.msg || "";
    res.send(`<h1>Echo: ${msg}</h1>`);
});

// Get all accounts state
app.get('/test/state', requireAuth, (req, res) => {
    res.json({ 
        accounts: accounts.map(a => ({ id: a.id, balance: a.balance, status: a.status })),
        transactions: transactions.length,
        transferDelayMs,
        freezeDuringTransfer
    });
});

app.listen(port, () => {
    console.log(`FinCore Test Server (Atomicity Testing) running on http://localhost:${port}`);
});
