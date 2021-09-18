const _ = require('lodash');

const bankAccount = {
    balance: 576,
    transactions: [
        {
            date: '2019-02-01',
            amount: 67
        },
        {
            date: '2019-02-02',
            amount: -45
        },
        {
            date: '2019-02-02',
            amount: -78
        },
        {
            date: '2019-02-02',
            amount: 90
        },
        {
            date: '2019-02-01',
            amount: -87
        },
        {
            date: '2019-01-28',
            amount: -23
        },
        {
            date: '2019-01-29',
            amount: 100
        },
        {
            date: '2019-01-28',
            amount: 25
        },
        {
            date: '2019-01-28',
            amount: -125
        },
        {
            date: '2019-01-28',
            amount: -24
        },
        {
            date: '2019-01-29',
            amount: 45
        },
    ]
};

function adjustBalance(balance, change) {
    if(change < 0) {
        balance += Math.abs(change);
    } else {
        balance -= change;
    }

    return balance;
}

const transactions = _.orderBy(bankAccount.transactions, 'date', 'desc');
let runningBalance = bankAccount.balance;
let currentDate = transactions[0].date;
let startingBalances = {};

for(let i = 0; i < transactions.length; i++) {
    if(transactions[i].date !== currentDate) {
        startingBalances[currentDate] = runningBalance;
        currentDate = transactions[i].date;
    }

    runningBalance = adjustBalance(runningBalance, transactions[i].amount);
}

startingBalances[currentDate] = runningBalance;

console.log(startingBalances);
