name: Pump Radar

on:
  schedule:
    - cron: '*/30 * * * *' # هر ۳۰ دقیقه یک‌بار اجرا می‌شود
  workflow_dispatch:      # اجازه اجرای دستی با دکمه

jobs:
  run-radar:
  runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Run Radar Script
        env:
          TG_TOKEN: ${{ secrets.TG_TOKEN }}
          TG_CHAT: ${{ secrets.TG_CHAT }}
        run: |
          python3 pump_radar.py
