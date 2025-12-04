# VPS Deployment Guide for Flattrade Trading Bot

This guide provides detailed, step-by-step instructions for deploying the Flattrade trading bot on a Virtual Private Server (VPS) running a modern Debian-based Linux distribution (like Ubuntu 20.04+).

Following these steps will help you set up a reliable, persistent trading environment.

---

## Part 1: Initial Server Setup

These steps are only required once when you first set up your VPS.

### Step 1: Connect to Your VPS
First, connect to your VPS using SSH. You will get the IP address and root password from your VPS provider.

```bash
ssh root@<YOUR_VPS_IP_ADDRESS>
```

### Step 2: Update Your System
It's crucial to start with an up-to-date system to ensure all packages are current and secure.

```bash
sudo apt update && sudo apt upgrade -y
```

### Step 3: Install Python and Pip
The bot requires Python. We will install Python 3, `pip` (the Python package installer), and `venv` (for creating virtual environments).

```bash
sudo apt install python3 python3-pip python3-venv -y
```

### Step 4: Clone the Trading Bot Repository
Clone the repository containing the trading bot code from your Git provider.

```bash
# Make sure you are in the home directory
cd ~

# Clone your repository (replace with your actual repo URL)
git clone <YOUR_GIT_REPOSITORY_URL>

# Navigate into the project directory
cd <YOUR_PROJECT_FOLDER_NAME>
```

### Step 5: Create a Virtual Environment
A virtual environment is essential for isolating the bot's dependencies from the system's Python packages.

```bash
# Create the virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```
**Note:** You will need to activate this virtual environment (`source venv/bin/activate`) every time you log in to a new terminal session to work on the bot.

### Step 6: Install Required Python Libraries
Install all the necessary Python libraries for the bot.

```bash
pip install requests pyyaml pandas
pip install https://github.com/flattrade/pythonAPI/raw/main/dist/NorenRestApi-0.0.29-py3-none-any.whl
```

---

## Part 2: Daily Operation

You will need to perform some of these steps daily to keep the bot running.

### Step 7: Generate Your Daily API Token
The Flattrade API requires a new token to be generated every day. The `token_generator` script from the official Flattrade repository is required for this.

**IMPORTANT:** This process requires you to open a URL in a local web browser. You must use an **SSH tunnel** to forward the port from your VPS to your local machine.

1.  **On Your Local Machine (NOT the VPS):** Open a new terminal and run this command. This will forward port 8080 from your VPS to your local machine.
    ```bash
    ssh -L 8080:localhost:8080 root@<YOUR_VPS_IP_ADDRESS>
    ```
2.  **In the New SSH Session:** Navigate to your project folder and run the token generator script (assuming you have cloned the official repo as instructed in the main `README.md`).
    ```bash
    cd ~/<YOUR_PROJECT_FOLDER_NAME>/pythonAPI-main/token_generator
    python gettoken.py
    ```
3.  **On Your Local Machine:** Copy the URL printed in the terminal (it will start with `http://localhost:8080`) and paste it into your local web browser. Log in and approve.
4.  **Back in the SSH Session:** Your `user_token` will be printed in the terminal. Copy this token.

### Step 8: Configure the Bot
Open the `config.py` file to update your credentials.

```bash
# Use a terminal-based text editor like nano
nano config.py
```
Update the `user_id` and paste the new daily `user_token`. Save the file by pressing `Ctrl+X`, then `Y`, then `Enter`.

### Step 9: Run the Bot Persistently with `tmux`
`tmux` is a terminal multiplexer that allows you to keep the bot running even after you disconnect from your SSH session.

1.  **Start a new `tmux` session:**
    ```bash
    tmux new -s trading_bot
    ```
2.  **Activate the virtual environment:**
    ```bash
    source venv/bin/activate
    ```
3.  **Run the bot:**
    ```bash
    python trading_bot.py
    ```
4.  **Detach from the `tmux` session:** Press `Ctrl+B` and then `D`. The bot is now running in the background.

### How to Manage Your `tmux` Session
*   **To re-attach to the session** (to view logs or stop the bot):
    ```bash
    tmux attach -t trading_bot
    ```
*   **To stop the bot:** While attached to the session, press `Ctrl+C`.
*   **To see a list of running sessions:**
    ```bash
    tmux ls
    ```
