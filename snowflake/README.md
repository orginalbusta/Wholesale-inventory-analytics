# Running on Snowflake (optional)

The default pipeline, CI and the public site all run on DuckDB for free. Snowflake is an optional
second target that runs **the same dlt loads and dbt project**. Phase 8 uses it to show the platform
on a cloud warehouse (build time, credits used, screenshots). All data is synthetic.

Setup takes about 15 minutes. Nothing here needs to be shared in chat or committed: secrets live in
`.env` (git-ignored) and in a key file outside the repo.

## 1. Start the trial

1. Sign up at <https://signup.snowflake.com/>. The 30-day trial includes free credits and needs no card.
2. Edition: **Standard** is enough. Cloud: **AWS**, region **US West (Oregon)** (any region works).
3. Activate the account from the email and sign in to **Snowsight** (the web UI).

## 2. Create a key pair (on your machine)

dbt and dlt sign in as a *service user* with an RSA key pair instead of a password. Run this in
**Git Bash** (it ships with OpenSSL). It asks for a passphrase twice; pick a new one and keep it
for step 4.

```bash
mkdir -p ~/.snowflake
openssl genrsa 2048 | openssl pkcs8 -topk8 -v2 aes-256-cbc -inform PEM -out ~/.snowflake/craftstones_rsa_key.p8
```

Then derive the public key (asks for the passphrase once):

```bash
openssl rsa -in ~/.snowflake/craftstones_rsa_key.p8 -pubout -out ~/.snowflake/craftstones_rsa_key.pub
```

Print the public key as one line, ready to paste into the setup script:

```bash
grep -v "PUBLIC KEY" ~/.snowflake/craftstones_rsa_key.pub | tr -d '\r\n'; echo
```

- `craftstones_rsa_key.p8` is the **private** key. It never leaves your machine and never goes in the repo (`*.p8` is git-ignored anyway).
- `craftstones_rsa_key.pub` is the **public** key. It's safe to paste into Snowflake.

## 3. Run the setup script (in Snowsight)

1. In Snowsight, open **Projects → Worksheets → + SQL Worksheet**.
2. Paste the contents of [`setup.sql`](setup.sql).
3. Change the two lines marked `CHANGE ME`:
   - `credit_quota = 10`: the monthly credit cap. An X-Small warehouse uses 1 credit per hour while running, and a medium build takes a few minutes, so 10 is generous.
   - `rsa_public_key = '...'`: paste the one-line public key from step 2 between the quotes.
4. Make sure the worksheet's role is **ACCOUNTADMIN**, then **Run All**.
5. The last four statements are checks. `DESCRIBE USER DBT_SVC` should show a value in the `RSA_PUBLIC_KEY_FP` row.

What it creates: an X-Small warehouse `CRAFTSTONES_WH` that suspends after 60 idle seconds, a
resource monitor that suspends it at your credit cap, a role `TRANSFORMER`, a database
`CRAFTSTONES_ANALYTICS`, and the service user `DBT_SVC`.

## 4. Fill in `.env`

Find your **account identifier**: in Snowsight, click your name (bottom left) → **Account** →
**View account details**. Copy the `Account identifier`, which looks like `ORGNAME-ACCOUNTNAME`.

Then add these lines to `.env` in the repo root (copy `.env.example` first if you have no `.env`):

```
SNOWFLAKE_ACCOUNT=ORGNAME-ACCOUNTNAME
SNOWFLAKE_USER=DBT_SVC
SNOWFLAKE_ROLE=TRANSFORMER
SNOWFLAKE_WAREHOUSE=CRAFTSTONES_WH
SNOWFLAKE_DATABASE=CRAFTSTONES_ANALYTICS
SNOWFLAKE_PRIVATE_KEY_PATH=C:/Users/<you>/.snowflake/craftstones_rsa_key.p8
SNOWFLAKE_PRIVATE_KEY_PASSPHRASE=<the passphrase from step 2>
```

Leave `WAREHOUSE=duckdb` as it is: the Snowflake runs set it per command, so the default
pipeline keeps using DuckDB.

## 5. Check the connection

Install the Snowflake extras, then ask dbt to connect. dbt doesn't read `.env` by itself, so pass
it with `--env-file`:

```bash
uv sync --all-groups --extra snowflake
```

```bash
uv run --env-file .env dbt debug --project-dir transform --profiles-dir transform --target snowflake
```

`All checks passed!` means you're ready. This briefly resumes the warehouse (a fraction of a credit).

## What happens next (Phase 8)

Once `dbt debug` passes, the Phase 8 run is: generate medium data, load it with dlt
(`WAREHOUSE=snowflake`), run `dbt build --target snowflake`, fix any differences between the
adapters, then record build time, credits used and a screenshot or two for the main README.
The public site and CI keep running on DuckDB.

Credits used so far (data can lag by up to a few hours), as ACCOUNTADMIN:

```sql
select warehouse_name, sum(credits_used) as credits
from snowflake.account_usage.warehouse_metering_history
where warehouse_name = 'CRAFTSTONES_WH'
group by 1;
```

## Clean up

When you're done, run [`teardown.sql`](teardown.sql) as ACCOUNTADMIN to drop everything the setup
created, or let the trial expire. Then delete the key files in `~/.snowflake/` and the
`SNOWFLAKE_*` lines in `.env`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `JWT token is invalid` | The public key in Snowflake doesn't match the private key file, or the user is wrong. Re-run the `alter user dbt_svc set rsa_public_key = ...` line with the current `.pub` contents |
| `Bad decrypt` / `incorrect password` | `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` doesn't match the passphrase used in step 2 |
| `Could not connect ... account` | `SNOWFLAKE_ACCOUNT` should be `ORGNAME-ACCOUNTNAME` (with a hyphen), not the full URL |
| `No active warehouse` / warehouse suspended by monitor | The credit cap was reached. Raise `credit_quota` on `CRAFTSTONES_MONITOR`, or wait for next month's reset |
