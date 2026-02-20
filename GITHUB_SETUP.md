# Push This Project to GitHub

## Option A: GitHub CLI (fastest)

If you have [GitHub CLI](https://cli.github.com/) installed and authenticated:

```powershell
cd "c:\Users\92025962\OneDrive - Anheuser-Busch InBev\Desktop\Bot"
.\scripts\push_to_github.ps1
```

## Option B: Manual steps

### 1. Install Git (if needed)

Download from https://git-scm.com/download/win and install.

### 2. Initialize and commit locally

Open PowerShell in the project folder and run:

```powershell
cd "c:\Users\92025962\OneDrive - Anheuser-Busch InBev\Desktop\Bot"

git init
git add -A
git commit -m "Initial commit: Polymarket BTC 15m HFT bot"
```

### 3. Create the repository on GitHub

1. Go to **https://github.com/new**
2. Repository name: `polymarket-btc-hft-bot` (or your choice)
3. Description: `24/7 HFT bot for Polymarket BTC 15-minute markets`
4. Choose **Public**
5. **Do NOT** check "Add a README" (we already have one)
6. Click **Create repository**

### 4. Push to GitHub

Replace `YOUR_USERNAME` with your GitHub username:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/polymarket-btc-hft-bot.git
git branch -M main
git push -u origin main
```

### 5. Authenticate

If Git prompts for credentials:

- **HTTPS**: Use a [Personal Access Token](https://github.com/settings/tokens) instead of your password
- **SSH**: Ensure your SSH key is added to GitHub and use:  
  `git remote set-url origin git@github.com:YOUR_USERNAME/polymarket-btc-hft-bot.git`

---

**Security reminder**: `.env`, `*.log`, and `*.csv` are in `.gitignore` and will **not** be pushed. Never commit your private key.
