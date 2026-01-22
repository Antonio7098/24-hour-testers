const express = require('express');
const bodyParser = require('body-parser');
const app = express();
const port = 3000;

app.enable('strict routing');
app.use(bodyParser.json());

// Rate Limiting Configuration
const RATE_LIMIT_WINDOW_MS = 30000; // 30 seconds
const RATE_LIMIT_MAX_REQUESTS = 20; // Max 20 requests per window

// Synchronous rate limit storage
const rateLimitStore = {};

// Use a module-level window tracker
let currentWindowStart = Math.floor(Date.now() / RATE_LIMIT_WINDOW_MS) * RATE_LIMIT_WINDOW_MS;

// Rate limiting middleware - synchronous to avoid race conditions
const rateLimit = (req, res, next) => {
    const auth = req.headers['x-fin-token'] || 'anonymous';
    const now = Date.now();
    
    // Update the window if needed
    const windowStart = Math.floor(now / RATE_LIMIT_WINDOW_MS) * RATE_LIMIT_WINDOW_MS;
    const windowKey = `${auth}:${windowStart}`;
    
    // Initialize if needed
    if (!rateLimitStore[windowKey]) {
        rateLimitStore[windowKey] = { count: 0, windowStart: windowStart };
    }
    
    const userData = rateLimitStore[windowKey];
    
    // Increment counter (synchronous operation)
    const newCount = ++userData.count;
    
    const remaining = Math.max(0, RATE_LIMIT_MAX_REQUESTS - newCount);
    const resetTime = windowStart + RATE_LIMIT_WINDOW_MS;
    
    // Add rate limit headers
    res.set('X-RateLimit-Limit', RATE_LIMIT_MAX_REQUESTS);
    res.set('X-RateLimit-Remaining', remaining);
    res.set('X-RateLimit-Reset', resetTime);
    
    if (newCount > RATE_LIMIT_MAX_REQUESTS) {
        const retryAfter = Math.ceil((resetTime - now) / 1000);
        res.set('Retry-After', retryAfter);
        
        res.status(429).json({
            error: "Too Many Requests",
            message: `Rate limit exceeded. Maximum ${RATE_LIMIT_MAX_REQUESTS} requests per ${RATE_LIMIT_WINDOW_MS / 1000} seconds.`,
            retry_after: retryAfter
        });
    } else {
        next();
    }
};

// In-memory database
const accounts = [
    { id: 101, owner: "Alice", balance: 5000.00, type: "checking" },
    { id: 102, owner: "Bob", balance: 150.00, type: "savings" },
    { id: 999, owner: "Admin", balance: 999999.00, type: "internal" }
];

let transactions = [
    { id: 1, account_id: 101, amount: -50.00, desc: "Grocery Store", date: "2025-01-01" },
    { id: 2, account_id: 102, amount: 500.00, desc: "Deposit", date: "2025-01-02" }
];

let processedIdempotencyKeys = new Set();

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
// BUG: Returns ALL accounts, including Admin and other users (IDOR/Info Leak)
app.get('/accounts', requireAuth, (req, res) => {
    res.json(accounts);
});

// 3. Get Transactions
app.get('/accounts/:id/transactions', requireAuth, (req, res) => {
    const accId = parseInt(req.params.id, 10);
    // Simple check: does account exist?
    const acc = accounts.find(a => a.id === accId);
    if (!acc) {
        return res.status(404).json({ error: "Account not found" });
    }
    
    // BUG: Missing ownership check. Alice can view Bob's transactions if she guesses ID.
    
    const accountTx = transactions.filter(t => t.account_id === accId);
    res.json(accountTx);
});

// 4. Transfer Funds
app.post('/transfer', requireAuth, rateLimit, (req, res) => {
    const { from_account, to_account, amount } = req.body;
    const idemKey = req.headers['idempotency-key'];

    // BUG: Idempotency key is read but NOT enforced. Replay attacks possible.
    if (idemKey && processedIdempotencyKeys.has(idemKey)) {
        // Mocking behavior: suppose we just say OK, but we don't actually stop the logic below in this buggy version?
        // Or let's say we ignore the key entirely for the bug.
    }

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

    if (source.balance < amount) {
        return res.status(400).json({ error: "Insufficient funds" });
    }

    // Process Transfer
    source.balance -= amount;
    dest.balance += amount;

    // Record Transaction
    const txId = transactions.length + 1;
    transactions.push({ id: txId, account_id: from_account, amount: -amount, desc: `Transfer to ${to_account}`, date: new Date().toISOString() });
    transactions.push({ id: txId + 1, account_id: to_account, amount: amount, desc: `Transfer from ${from_account}`, date: new Date().toISOString() });

    if (idemKey) processedIdempotencyKeys.add(idemKey);

    res.json({ status: "success", tx_id: txId, new_balance: source.balance });
});

// 5. Admin Debug - Major Security Risk
// BUG: No extra auth required, accessible by anyone with basic token. Leaks internal config.
app.get('/admin/debug', requireAuth, (req, res) => {
    res.json({
        env: process.env,
        memory: process.memoryUsage(),
        db_dump: { accounts, transactions }
    });
});

app.post('/admin/reset', requireAuth, (req, res) => {
    const body = req.body || {};
    const target_balance = parseFloat(req.query.balance || body.balance) || 5000;
    accounts[0].balance = target_balance;
    accounts[1].balance = 150.00;
    accounts[2].balance = 999999.00;
    transactions = [
        { id: 1, account_id: 101, amount: -50.00, desc: "Grocery Store", date: "2025-01-01" },
        { id: 2, account_id: 102, amount: 500.00, desc: "Deposit", date: "2025-01-02" }
    ];
    processedIdempotencyKeys.clear();
    res.json({ status: "reset", accounts: accounts });
});

// 6. Undocumented 'echo' endpoint that is vulnerable to XSS/Reflected input
app.get('/utils/echo', (req, res) => {
    const msg = req.query.msg || "";
    // BUG: Returns HTML with unsanitized input
    res.send(`<h1>Echo: ${msg}</h1>`);
});

app.listen(port, () => {
    console.log(`FinCore SUT running on http://localhost:${port}`);
});
