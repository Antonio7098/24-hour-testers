
const express = require('express');
const app = express();
app.use(express.json());

const DELAY_BEFORE_BALANCE_READ = 50;
const DELAY_BEFORE_CHECK = 20;
const DELAY_BEFORE_COMMIT = 30;

let accounts = [
    { id: 101, owner: "Alice", balance: 5000, type: "checking" },
    { id: 102, owner: "Bob", balance: 750, type: "savings" },
    { id: 999, owner: "Admin", balance: 999999, type: "internal" }
];

let transactions = [];
let processedKeys = new Set();

app.get('/health', (req, res) => res.json({ status: "ok" }));

app.get('/accounts', (req, res) => {
    res.json(accounts);
});

app.get('/accounts/:id/transactions', (req, res) => {
    const id = parseInt(req.params.id);
    const txns = transactions.filter(t => t.account_id === id);
    res.json(txns);
});

app.post('/transfer', async (req, res) => {
    const { from_account, to_account, amount } = req.body;
    const idempotencyKey = req.headers['idempotency-key'];
    
    if (processedKeys.has(idempotencyKey)) {
        return res.status(200).json({ 
            status: "already_processed",
            message: "Duplicate request",
            idempotency_key: idempotencyKey
        });
    }
    
    await new Promise(r => setTimeout(r, DELAY_BEFORE_BALANCE_READ));
    
    const source = accounts.find(a => a.id === from_account);
    const dest = accounts.find(a => a.id === to_account);
    
    if (!source || !dest) {
        return res.status(404).json({ error: "Account not found" });
    }
    
    await new Promise(r => setTimeout(r, DELAY_BEFORE_CHECK));
    
    if (source.balance < amount) {
        return res.status(400).json({ 
            error: "Insufficient funds",
            balance: source.balance,
            requested: amount
        });
    }
    
    await new Promise(r => setTimeout(r, DELAY_BEFORE_COMMIT));
    
    source.balance -= amount;
    dest.balance += amount;
    
    const txn = {
        id: transactions.length + 1,
        account_id: from_account,
        amount: -amount,
        desc: `Transfer to ${to_account}`,
        date: new Date().toISOString()
    };
    transactions.push(txn);
    
    processedKeys.add(idempotencyKey);
    
    res.json({
        status: "success",
        from_balance: source.balance,
        to_balance: dest.balance,
        amount: amount
    });
});

app.get('/admin/debug', (req, res) => {
    res.json({
        accounts: accounts,
        transactions: transactions,
        processed_keys_count: processedKeys.size
    });
});

app.get('/admin/reset', (req, res) => {
    accounts = [
        { id: 101, owner: "Alice", balance: 5000, type: "checking" },
        { id: 102, owner: "Bob", balance: 750, type: "savings" },
        { id: 999, owner: "Admin", balance: 999999, type: "internal" }
    ];
    transactions = [];
    processedKeys.clear();
    res.json({ status: "reset" });
});

const PORT = 3001;
app.listen(PORT, () => {
    console.log(`[PATCHED SERVER] Running on port ${PORT}`);
    console.log(`Delays: read=${50}ms, check=${20}ms, commit=${30}ms`);
});
