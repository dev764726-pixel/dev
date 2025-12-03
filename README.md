# Flattrade Algo-Trading Bot: Setup Guide

This guide provides a complete, step-by-step walkthrough to set up and run your trading bot using the official Flattrade Python API.

**IMPORTANT:** This bot uses a token-based authentication system. You must generate a new `user_token` every day after 5:00 AM IST to run the bot.

---

## Part 1: One-Time Setup

### Step 1: Download the Official API Repository
The token generation script is part of the official Flattrade API repository. You need to download it first.

1.  Go to [https://github.com/flattrade/pythonAPI](https://github.com/flattrade/pythonAPI).
2.  Click the green **"Code"** button and select **"Download ZIP"**.
3.  Extract the ZIP file to a known location on your computer (e.g., your `Downloads` folder).

### Step 2: Create Your Project in PyCharm
1.  Open PyCharm and create a new project (**File > New Project**).
2.  Choose a location and name (e.g., `my_trading_bot`).
3.  Ensure **"New environment using: Virtualenv"** is selected and click **Create**.

### Step 3: Create the Project Files
1.  In the Project panel on the left, right-click your project folder.
2.  Select **New > Python File** and create `config.py`.
3.  Repeat to create `trading_bot.py`.

### Step 4: Install Required Libraries
1.  Open the **Terminal** tab at the bottom of PyCharm.
2.  Copy and paste the following commands one by one, pressing Enter after each:
    ```bash
    pip install requests pyyaml pandas pandas-ta
    ```
    ```bash
    pip install https://github.com/flattrade/pythonAPI/raw/main/dist/NorenRestApi-0.0.29-py3-none-any.whl
    ```

### Step 5: Add the Code to Your Files
Copy the code I have provided for `config.py` and `trading_bot.py` and paste it into the corresponding files in PyCharm.

---

## Part 2: Daily Token Generation

You must perform these steps every day you wish to run the bot.

### Step 6: Generate Your Daily Token
1.  Navigate to the `pythonAPI-main/token_generator` directory inside the folder you downloaded and extracted in Step 1.
2.  Follow the instructions in the `setup.md` file within that directory, or follow this summary:
    *   Open `gettoken.py` and enter your Flattrade **API Key** and **Secret Key**.
    *   Run the script: `python gettoken.py`.
    *   The script will print a URL. Copy this URL and paste it into your web browser.
    *   Log in to your Flattrade account and approve the application.
    *   You will be redirected to a blank page. The URL of this page will contain your request token (e.g., `http://localhost:8080/?request_token=YOUR_TOKEN_IS_HERE`).
3.  The terminal running `gettoken.py` will now have printed your **`user_token`**. It's a very long string. This is the token you need for the bot.

---

## Part 3: Running the Bot

### Step 7: Configure Your Credentials
1.  Open the `config.py` file in your PyCharm project.
2.  Fill in your `user_id` and paste the daily `user_token` you just generated.

    ```python
    # config.py
    user_id = "FA12345"  # Your Flattrade User ID
    user_token = "PASTE_THE_LONG_TOKEN_STRING_HERE"
    ```
3.  Save the file.

### Step 8: Run the Trading Bot
1.  Open `trading_bot.py` in the editor.
2.  Right-click anywhere inside the code and select **Run 'trading_bot'**.

The bot will start, set its session using your token, and begin executing the strategy. Remember to generate and paste a new token every day!

---

## Part 4: VPS Deployment

For instructions on how to deploy and run this bot on a Virtual Private Server (VPS) for persistent, 24/7 operation, please see the detailed guide:

- [**VPS Deployment Guide**](./VPS_DEPLOYMENT_GUIDE.md)