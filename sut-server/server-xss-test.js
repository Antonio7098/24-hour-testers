const express = require('express');
const bodyParser = require('body-parser');
const app = express();
const port = 3002;

app.enable('strict routing');
app.use(bodyParser.json());

const RATE_LIMIT_WINDOW_MS = 30000;
const RATE_LIMIT_MAX_REQUESTS = 20;
const rateLimitStore = {};
let currentWindowStart = Math.floor(Date.now() / RATE_LIMIT_WINDOW_MS) * RATE_LIMIT_WINDOW_MS;

const rateLimit = (req, res, next) => {
    const auth = req.headers['x-fin-token'] || 'anonymous';
    const now = Date.now();
    const windowStart = Math.floor(now / RATE_LIMIT_WINDOW_MS) * RATE_LIMIT_WINDOW_MS;
    const windowKey = `${auth}:${windowStart}`;
    if (!rateLimitStore[windowKey]) {
        rateLimitStore[windowKey] = { count: 0, windowStart: windowStart };
    }
    const userData = rateLimitStore[windowKey];
    const newCount = ++userData.count;
    const remaining = Math.max(0, RATE_LIMIT_MAX_REQUESTS - newCount);
    const resetTime = windowStart + RATE_LIMIT_WINDOW_MS;
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
    res.json(accountTx);
});

app.post('/transfer', requireAuth, rateLimit, (req, res) => {
    const { from_account, to_account, amount, description } = req.body;
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

    if (source.balance < amount) {
        return res.status(400).json({ error: "Insufficient funds" });
    }

    source.balance -= amount;
    dest.balance += amount;

    const txId = transactions.length + 1;
    const desc = description || `Transfer to ${to_account}`;
    transactions.push({ id: txId, account_id: from_account, amount: -amount, desc: desc, date: new Date().toISOString() });
    transactions.push({ id: txId + 1, account_id: to_account, amount: amount, desc: `Transfer from ${from_account}`, date: new Date().toISOString() });

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

app.get('/utils/echo', (req, res) => {
    const msg = req.query.msg || "";
    res.send(`<h1>Echo: ${msg}</h1>`);
});

app.listen(port, () => {
    console.log(`FinCore SUT (XSS Test Variant) running on http://localhost:${port}`);
    console.log(`NOTE: This version accepts 'description' field in transfers for XSS testing`);
});
