---
raw_hash: a781640e06adb199ecd9213ed2acd34fc71b1c870db50209c537870c470a2d78
source_filename: Mahima.xlsx
flagged_at: 2026-08-16T13:22:15.245146+00:00
reason: "Introduces multiple new entities' sensitive banking credentials, credit card numbers, and payroll data with no clear existing directory page to update, overlapping ambiguously with the existing SVB checking account page and containing unresolved figures (e.g., Rajat's LOC limit, an unclear salary revision note)."
candidate_target: vault/04-finance/banking-accounts-overview.md
confidence: low
---

## Extracted content
## Sheet: Framework
Rajat Jain | live in Canada | Ashima Naval
Saving Account | Dormant
1.0 | Personal Account | Canada | Current Account | 4.0 | Personal Account | Canada | Current Account
Credit Card | Credit Card
Line of Credit | 10000.0 | Line of Credit | 10000.0
2.0 | Company Account | Prata Inc. - Canada | Operating account | dormant | 5.0 | Company Account | 142577 ontario inc.  | Operating account
Credit Card  | Dormant | Credit Card 
Line of Credit | 20000.0
3.0 | Company Account | Prata Inc - USA | Checking Account
Credit card
Splitvise 
## Sheet: Credentials
List of things you need from us.  | Account Number | Net Banking Credtentials (to access statements)
Username | Password
Savings Account (Ashima) | 010-03022-6207499 | 4506 4460 3276 1914 | Ashima19! | CIBC (Canadian Imperial bank of commerce) | You need to know the following
What dates are all the credit card payments due on
Current Accounts | what date all the line of credit interest payment are due on. 
Personal - Rajat (CA) | 003-00472-5155577 | 4519025386255262 | aashima12 | Rbcroyalbank.com | which transaction happen on my personal credit card however, they are my business expenses. So that at the end of the year, we can write off all those expenses. 
001-01678-1011873 | 4519023315481075 | Socialtutors1! | Rbcroyalbank.com | What employees in have and how much salaries we have to pay them monthly _ will have to connect you with remya to sort that out. 
001 00472-1049667 | 4519023156472712 | Socialtutors1! | Rbcroyalbank.com | Noted all the points.
Prata (CA) | I just first want to first analyse the statements so that I could get an idea of monthly no of trascations and their flow.
Prata (USA) | Rajateoxs | Socialtutors8! | Svbconnect.com | Once I go through of it, then I will start working on categorization in which I would need all the details you've mentioned above.
Accountseoxs | Socialtutors1! | Svbconnect.com | You can also put them now if you've time
14775261 ontario inc. (Ashima - CA) | 010-08132- 1083511 | 4506  4490 7459 1215 | Ashima19! | CIBC (Canadian Imperial bank of commerce)
Personal - Ashima (CA) | 010-03022- 6207480 | 4506 4460 3276 1914 | Ashima19! | CIBC (Canadian Imperial bank of commerce)
Credit Card | Number | Expiry | CVV | Credit Card Payment Due Date
Personal - Rajat (CA) | 12th of every month  | Rbcroyalbank.com
Prata (CA)
Prata (USA) | 5104-4680-0028-5695 | 2024-08-01 00:00:00 | 249.0 | 26th of every month  | Svbconnect.com
Personal - Ashima (CA) | 4500 5303 4397 7094 | 2024-09-26 00:00:00 | 21st of every month | CIBC (Canadian Imperial bank of commerce)
14775261 ontario inc. (Ashima - CA) | 4500 0410 4123 8594 | 2024-12-26 00:00:00 | 29th  of every month | CIBC (Canadian Imperial bank of commerce)
Limit Accounts
Personal - Rajat (CA) | Any detail of limit accounts? 
Prata (CA) | 10000.0
Personal - Ashima (CA) | 20000.0
30000.0
Splitvise (will start this one after sorting the bank accounts)
would be helpful if got an intro with accountant. It will help to work accordingly as needed.
## Sheet: Salaries info
Payroll Details
Bank Name | IFSC Code | A/C No | Name on A/C | Phone Number | Salaries/ month
Bank of Baroda | BARB0GRAINM (fifth character is a zero) | 33780100007256.0 | Ranjan Jain | 8360221257.0 | 20000.0 | 300000 from Feb' 2023
Bank of India | BKID0006963 | 696310110011300.0 | Mohd Shazeb | 911811366.0 | 18000.0
HDFC Bank Ltd. | HDFC0004396 | 50100304920178.0 | Remya Mohanan | 9654471330.0 | 55000.0
Indusind bank | INDB0000789 | 100094217341.0 | Harmanjeet singh | 8727020040.0 | Contractual
HDFC Bank Ltd. | HDFC0000029 | 298620000014.0 | Pragmatic Techsoft Pvt. Ltd. | NA
## Sheet: Questions
You need to know the following
What dates are all the credit card payments due on
what date all the line of credit interest payment are due on. 
which transaction happen on my personal credit card however, they are my business expenses. So that at the end of the year, we can write off all those expenses. 
What employees in have and how much salaries we have to pay them monthly _ will have to connect you with remya to sort that out. 
Noted all the points.
I just first want to first analyse the statements so that I could get an idea of monthly no of trascations and their flow.
Once I go through of it, then I will start working on categorization in which I would need all the details you've mentioned above.
You can also put them now if you've time

## What the agent would have done
## Banking, Credit Card & Payroll Overview (Rajat Jain / Ashima Naval / Prata Inc.)

**Source:** Mahima.xlsx (internal framework/credentials/payroll tracker)
**Context:** Rajat Jain lives in Canada; entities involved include Rajat (personal), Ashima Naval (personal), Prata Inc. (Canada & USA), 142577 Ontario Inc., 14775261 Ontario Inc.

⚠️ This document contains live account numbers, credit card numbers, CVVs, and online banking passwords. Flagging for review before filing into the vault given the sensitivity and because it's unclear how this should integrate with the existing SVB checking account page (Prata Inc - USA) and whether other pages for these accounts already exist elsewhere in the vault.

### Framework / Account Structure

| # | Type | Entity | Account Type | Status | Notes |
|---|------|--------|--------------|--------|-------|
| 1.0 | Personal Account | Canada (Rajat) | Current Account | | Also has Savings Account - Dormant |
| | | | Credit Card | | |
| | | | Line of Credit | | Limit: $10,000 |
| 2.0 | Company Account | Prata Inc. - Canada | Operating account | Dormant | |
| | | | Credit Card | Dormant | |
| | | | Line of Credit | | Limit: $20,000 |
| 3.0 | Company Account | Prata Inc - USA | Checking Account | | Also has Credit Card, Splitvise |
| 4.0 | Personal Account | Canada (Ashima) | Current Account | | |
| | | | Credit Card | | |
| | | | Line of Credit | | Limit: $10,000 |
| 5.0 | Company Account | 142577 Ontario Inc. | Operating account | | Also has Credit Card |

### Credentials (Account Numbers & Net Banking) — SENSITIVE

| Account | Account Number | Card Number | Password | Bank |
|---|---|---|---|---|
| Savings Account (Ashima) | 010-03022-6207499 | 4506 4460 3276 1914 | Ashima19! | CIBC |
| Personal - Rajat (CA), account 1 | 003-00472-5155577 | 4519025386255262 | aashima12 | RBC Royal Bank (Rbcroyalbank.com) |
| Personal - Rajat (CA), account 2 | 001-01678-1011873 | 4519023315481075 | Socialtutors1! | RBC Royal Bank |
| Personal - Rajat (CA), account 3 | 001-00472-1049667 | 4519023156472712 | Socialtutors1! | RBC Royal Bank |
| Prata (USA) - main | (username: Rajateoxs) | | Socialtutors8! | Svbconnect.com (SVB) |
| Prata (USA) - accounts login | (username: Accountseoxs) | | Socialtutors1! | Svbconnect.com (SVB) |
| 14775261 Ontario Inc. (Ashima - CA) | 010-08132-1083511 | 4506 4490 7459 1215 | Ashima19! | CIBC |
| Personal - Ashima (CA) | 010-03022-6207480 | 4506 4460 3276 1914 | Ashima19! | CIBC |

### Credit Cards - Details & Due Dates

| Account | Card Number | Expiry | CVV | Due Date | Bank |
|---|---|---|---|---|---|
| Personal - Rajat (CA) | | | | 12th of every month | RBC Royal Bank |
| Prata (USA) | 5104-4680-0028-5695 | 2024-08-01 | 249 | 26th of every month | SVB (Svbconnect.com) |
| Personal - Ashima (CA) | 4500 5303 4397 7094 | 2024-09-26 | | 21st of every month | CIBC |
| 14775261 Ontario Inc. (Ashima - CA) | 4500 0410 4123 8594 | 2024-12-26 | | 29th of every month | CIBC |

### Line of Credit Limits

| Account | Limit |
|---|---|
| Personal - Rajat (CA) | (unspecified in source — flagged as open question in doc) |
| Prata (CA) | $10,000 |
| Personal - Ashima (CA) | $20,000 |
| (unlabeled, possibly 142577 Ontario Inc.) | $30,000 |

Note: "Splitvise" (likely Splitwise) mentioned as something to set up after bank accounts are sorted. Also noted: would like an introduction to an accountant.

### Payroll / Salaries Info

| Bank Name | IFSC Code | Account Number | Name on Account | Phone Number | Salary/Month |
|---|---|---|---|---|---|
| Bank of Baroda | BARB0GRAINM | 33780100007256 | Ranjan Jain | 8360221257 | 20,000 (300,000 from Feb 2023 — appears to be annual or revised figure, unclear) |
| Bank of India | BKID0006963 | 696310110011300 | Mohd Shazeb | 911811366 | 18,000 |
| HDFC Bank Ltd. | HDFC0004396 | 50100304920178 | Remya Mohanan | 9654471330 | 55,000 |
| IndusInd Bank | INDB0000789 | 100094217341 | Harmanjeet Singh | 8727020040 | Contractual |
| HDFC Bank Ltd. | HDFC0000029 | 298620000014 | Pragmatic Techsoft Pvt. Ltd. | NA | (vendor/contractor, not employee?) |

### Open Questions / Action Items (from source doc)
- What dates are all credit card payments due on (partially answered above, some still missing)
- What dates are line of credit interest payments due on (not yet answered)
- Identify personal credit card transactions that are actually business expenses (for year-end write-offs)
- Determine full employee list and monthly salary obligations (coordinate with Remya)
- Plan to first analyze statements to understand monthly transaction volume/flow before categorizing
- Requested introduction to an accountant

### Reason for review
This spreadsheet introduces many new sensitive banking/credit-card credentials and payroll figures for multiple entities (Rajat, Ashima, Prata Inc CA/USA, 142577 & 14775261 Ontario Inc.) with no clear existing "account directory" page in the vault to update — it partially overlaps with the existing SVB checking account page (same Prata Inc - USA entity) but doesn't clearly supersede it, and several figures (e.g., Rajat's line of credit limit, the "300000 from Feb 2023" salary note) are ambiguous. A human should confirm the correct target page(s) and whether storing raw credentials/CVVs in the vault as plaintext is acceptable.

