from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
import io
import os
import hashlib
import secrets as _secrets_mod
import pandas as pd
import numpy as np
from datetime import datetime
import glob as glob_mod

# Load .env file if present (for Kpler credentials etc.)
_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.isfile(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                if _k.strip() not in os.environ:
                    os.environ[_k.strip()] = _v.strip()
# Lazy-import sklearn to reduce startup memory (saves ~200MB)
_sklearn_loaded = False
RandomForestClassifier = None
GradientBoostingClassifier = None
StandardScaler = None

def _ensure_sklearn():
    global _sklearn_loaded, RandomForestClassifier, GradientBoostingClassifier, StandardScaler
    if not _sklearn_loaded:
        from sklearn.ensemble import RandomForestClassifier as _RFC, GradientBoostingClassifier as _GBC
        from sklearn.preprocessing import StandardScaler as _SS
        RandomForestClassifier = _RFC
        GradientBoostingClassifier = _GBC
        StandardScaler = _SS
        _sklearn_loaded = True
import openpyxl
import warnings
warnings.filterwarnings("ignore")

app = FastAPI(title="Crude Oil Futures Backtesting Platform")

# ------------- Password Gate (shared password) ----------------
_APP_PASSWORD = os.environ.get("APP_PASSWORD", "CrudeOil$Analyt1cs#2026!Secure")
_AUTH_SECRET = hashlib.sha256((_APP_PASSWORD + "_coa_signing_key").encode()).hexdigest()
# Shared token used by the local Bloomberg bridge to push live prices. Defaults
# to a value derived from the app password so it works without extra config, but
# should be overridden with LIVE_INGEST_TOKEN in production.
_LIVE_INGEST_TOKEN = os.environ.get(
    "LIVE_INGEST_TOKEN",
    hashlib.sha256((_APP_PASSWORD + "_live_ingest").encode()).hexdigest()[:32],
)


def hmac_compare(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(str(a), str(b))


_LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Login — Crude Oil Analytics</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#0a0f1a;font-family:'Inter',system-ui,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;color:#e2e8f0}
  .card{background:#111827;border:1px solid #1e293b;border-radius:16px;padding:40px;width:380px;box-shadow:0 20px 60px rgba(0,0,0,.5)}
  h1{font-size:20px;font-weight:800;color:#f59e0b;margin-bottom:6px;text-align:center}
  .sub{font-size:12px;color:#64748b;text-align:center;margin-bottom:28px}
  label{font-size:11px;color:#94a3b8;text-transform:uppercase;font-weight:600;letter-spacing:.05em;display:block;margin-bottom:6px}
  input{width:100%;padding:12px 14px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:14px;outline:none;transition:border .2s}
  input:focus{border-color:#f59e0b}
  button{width:100%;margin-top:20px;padding:12px;background:linear-gradient(135deg,#f59e0b,#d97706);color:#000;border:none;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;transition:opacity .2s}
  button:hover{opacity:.9}
  .err{color:#ef4444;font-size:12px;text-align:center;margin-top:12px;display:none}
</style>
</head>
<body>
<div class="card">
  <h1>Crude Oil Analytics</h1>
  <div class="sub">Enter the access password to continue</div>
  <form method="POST" action="/auth/login">
    <label for="pw">Password</label>
    <input type="password" id="pw" name="password" placeholder="Enter password" autofocus required>
    <button type="submit">Sign In</button>
    <div class="err" id="err">__ERROR__</div>
  </form>
</div>
</body>
</html>
"""


_STATIC_EXTS = {".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".woff", ".woff2", ".ttf", ".map", ".webp", ".gif"}


def _make_session_token() -> str:
    """Create an HMAC-signed session token that any machine can verify."""
    import hmac
    payload = "authenticated"
    sig = hmac.new(_AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _verify_session_token(token: str) -> bool:
    """Verify an HMAC-signed session token (works across all machines)."""
    import hmac
    if not token or ":" not in token:
        return False
    payload, sig = token.rsplit(":", 1)
    expected = hmac.new(_AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


class PasswordGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/auth/"):
            return await call_next(request)
        # Allow static assets through (no sensitive data)
        if any(path.endswith(ext) for ext in _STATIC_EXTS) or path.startswith("/assets/"):
            return await call_next(request)
        token = request.cookies.get("coa_session")
        if token and _verify_session_token(token):
            return await call_next(request)
        # Live price / positioning ingest from the local Bloomberg bridge
        # authenticates with a shared token header instead of a session cookie.
        if path in ("/api/pricing/live", "/api/positioning/live", "/api/voloi/live") and request.method == "POST":
            ingest = request.headers.get("x-ingest-token", "")
            if ingest and _LIVE_INGEST_TOKEN and hmac_compare(ingest, _LIVE_INGEST_TOKEN):
                return await call_next(request)
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if path.startswith("/api/"):
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        # Redirect to login page (avoids browser cache issues)
        return RedirectResponse(url="/auth/login", status_code=302)


app.add_middleware(PasswordGateMiddleware)


@app.get("/auth/login")
async def auth_login_page():
    return HTMLResponse(_LOGIN_PAGE.replace("__ERROR__", ""))


@app.post("/auth/login")
async def auth_login(password: str = Form(...)):
    if password == _APP_PASSWORD:
        token = _make_session_token()
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie("coa_session", token, httponly=True, samesite="lax", max_age=86400 * 30)
        return response
    err_page = _LOGIN_PAGE.replace("__ERROR__", "Incorrect password").replace('display:none', 'display:block')
    return HTMLResponse(err_page, status_code=200)


@app.get("/auth/logout")
async def auth_logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("coa_session")
    return response


# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# In-memory storage
datasets: dict[str, dict] = {}
combinations: dict[str, dict] = {}
backtests: dict[str, dict] = {}


# Detect Fly.io or explicit LEAN_MODE to reduce startup memory
_LEAN_MODE = os.environ.get("LEAN_MODE", "").lower() in ("1", "true", "yes") or os.environ.get("FLY_APP_NAME", "") != ""

# --- Auto-load sample CSV on startup ---
@app.on_event("startup")
async def load_sample_data():
    """Auto-load sample_crude.csv and essential data on startup."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    candidates = [
        os.path.join(base_dir, "sample_crude.csv"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_crude.csv"),
    ]
    # Also search common locations
    candidates += glob_mod.glob("/home/ubuntu/crude-oil-original/sample_crude.csv")
    for path in candidates:
        if os.path.isfile(path):
            try:
                df = pd.read_csv(path)
                date_col = None
                for col in df.columns:
                    if col.lower() in ["date", "dates", "timestamp", "time", "datetime"]:
                        date_col = col
                        break
                if date_col is None:
                    try:
                        pd.to_datetime(df.iloc[:, 0])
                        date_col = df.columns[0]
                    except (ValueError, TypeError):
                        pass
                if date_col:
                    df[date_col] = pd.to_datetime(df[date_col])
                    df = df.sort_values(date_col).reset_index(drop=True)
                dataset_id = "sample01"
                numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                datasets[dataset_id] = {
                    "id": dataset_id,
                    "name": os.path.basename(path),
                    "date_column": date_col,
                    "columns": df.columns.tolist(),
                    "numeric_columns": numeric_cols,
                    "row_count": len(df),
                    "uploaded_at": datetime.utcnow().isoformat(),
                    "dataframe": df,
                }
                print(f"[STARTUP] Auto-loaded sample data: {path} ({len(df)} rows)")
            except Exception as e:
                print(f"[STARTUP] Failed to load sample data: {e}")
            break
    
    # Auto-load instrument Excel files
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    if not os.path.isdir(data_dir):
        data_dir = "/app/data"
    if not os.path.isdir(data_dir):
        data_dir = "/home/ubuntu/crude-oil-original/data"
    
    instrument_files = [
        ("flat_price_brent.xlsx", "flat+price+brent.xlsx"),
        ("spread_brent.xlsx", "testconq.xlsx"),
    ]
    
    for fname, orig_name in instrument_files:
        fpath = os.path.join(data_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, "rb") as f:
                content = f.read()
            parsed = _parse_instrument_excel(content, orig_name)
            import hashlib
            inst_id = hashlib.md5(orig_name.encode()).hexdigest()[:8]
            instruments[inst_id] = {
                "id": inst_id,
                "name": parsed["instrument_name"],
                "filename": orig_name,
                "timeframes": parsed["timeframes"],
                "uploaded_at": datetime.utcnow().isoformat(),
            }
            tf_list = list(parsed["timeframes"].keys())
            print(f"[STARTUP] Auto-loaded instrument: {parsed['instrument_name']} ({orig_name}) -> {inst_id}, timeframes: {tf_list}")
        except Exception as e:
            print(f"[STARTUP] Failed to load instrument {fname}: {e}")
    
    # Auto-load COT data - prefer COTnew.xlsx, fallback to cot_data.xlsx
    cot_path = os.path.join(data_dir, "COTnew.xlsx")
    if not os.path.isfile(cot_path):
        cot_path = os.path.join(data_dir, "cot_data.xlsx")
    if os.path.isfile(cot_path):
        try:
            with open(cot_path, "rb") as f:
                content = f.read()
            parsed = _parse_cot_excel(content)
            cot_data.clear()
            cot_data["categories"] = parsed
            cot_data["filename"] = os.path.basename(cot_path)
            cot_data["uploaded_at"] = datetime.utcnow().isoformat()
            cat_list = list(parsed.keys())
            total_rows = sum(c["row_count"] for c in parsed.values())
            print(f"[STARTUP] Auto-loaded COT data: {cat_list}, {total_rows} total rows")
        except Exception as e:
            print(f"[STARTUP] Failed to load COT data: {e}")

    # Auto-load CO1/CO2 price data from COTnew.xlsx
    cotnew_path = os.path.join(data_dir, "COTnew.xlsx")
    if os.path.isfile(cotnew_path):
        try:
            _load_co_price_data(cotnew_path)
        except Exception as e:
            print(f"[STARTUP] Failed to load CO1/CO2 data: {e}")

    # Auto-load multi-commodity COT data (Brent, WTI, Gasoil) — handled by separate startup event


# --- Models ---

class CombinationLeg(BaseModel):
    dataset_id: str
    column: str
    weight: float  # positive = long, negative = short


class CombinationCreate(BaseModel):
    name: str
    legs: list[CombinationLeg]


class SignalConfig(BaseModel):
    signal_type: str  # "ma_crossover", "zscore", "rsi", "bollinger", "threshold"
    params: dict


class BacktestRequest(BaseModel):
    name: str
    combination_id: str
    signal: SignalConfig
    position_size: float = 1.0
    transaction_cost: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


# --- Health ---

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# --- Dataset Endpoints ---

@app.post("/api/upload")
async def upload_dataset(file: UploadFile = File(...)):
    try:
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))

        date_col = None
        for col in df.columns:
            if col.lower() in ["date", "dates", "timestamp", "time", "datetime"]:
                date_col = col
                break

        if date_col is None:
            try:
                pd.to_datetime(df.iloc[:, 0])
                date_col = df.columns[0]
            except (ValueError, TypeError):
                pass

        if date_col:
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.sort_values(date_col).reset_index(drop=True)

        dataset_id = str(uuid.uuid4())[:8]
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        datasets[dataset_id] = {
            "id": dataset_id,
            "name": file.filename or "unnamed",
            "date_column": date_col,
            "columns": df.columns.tolist(),
            "numeric_columns": numeric_cols,
            "row_count": len(df),
            "uploaded_at": datetime.utcnow().isoformat(),
            "dataframe": df,
        }

        return {
            "id": dataset_id,
            "name": file.filename,
            "date_column": date_col,
            "columns": df.columns.tolist(),
            "numeric_columns": numeric_cols,
            "row_count": len(df),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")


@app.get("/api/datasets")
async def list_datasets():
    return [
        {
            "id": d["id"],
            "name": d["name"],
            "date_column": d["date_column"],
            "columns": d["columns"],
            "numeric_columns": d["numeric_columns"],
            "row_count": d["row_count"],
            "uploaded_at": d["uploaded_at"],
        }
        for d in datasets.values()
    ]


@app.get("/api/datasets/{dataset_id}")
async def get_dataset(dataset_id: str):
    if dataset_id not in datasets:
        raise HTTPException(status_code=404, detail="Dataset not found")

    d = datasets[dataset_id]
    df = d["dataframe"]

    records = []
    for _, row in df.iterrows():
        record = {}
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                record[col] = None
            elif isinstance(val, (pd.Timestamp, datetime)):
                record[col] = val.isoformat()
            elif isinstance(val, (np.integer,)):
                record[col] = int(val)
            elif isinstance(val, (np.floating,)):
                record[col] = float(val)
            else:
                record[col] = val
        records.append(record)

    return {
        "id": d["id"],
        "name": d["name"],
        "date_column": d["date_column"],
        "columns": d["columns"],
        "numeric_columns": d["numeric_columns"],
        "row_count": d["row_count"],
        "data": records,
    }


@app.delete("/api/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str):
    if dataset_id not in datasets:
        raise HTTPException(status_code=404, detail="Dataset not found")
    del datasets[dataset_id]
    return {"status": "deleted"}


# --- Combination Endpoints ---

@app.post("/api/combinations")
async def create_combination(combo: CombinationCreate):
    for leg in combo.legs:
        if leg.dataset_id not in datasets:
            raise HTTPException(status_code=404, detail=f"Dataset {leg.dataset_id} not found")
        if leg.column not in datasets[leg.dataset_id]["numeric_columns"]:
            raise HTTPException(
                status_code=400,
                detail=f"Column {leg.column} not found or not numeric in dataset {leg.dataset_id}",
            )

    combo_id = str(uuid.uuid4())[:8]
    combinations[combo_id] = {
        "id": combo_id,
        "name": combo.name,
        "legs": [leg.model_dump() for leg in combo.legs],
        "created_at": datetime.utcnow().isoformat(),
    }

    return {"id": combo_id, "name": combo.name, "legs": combinations[combo_id]["legs"]}


@app.get("/api/combinations")
async def list_combinations():
    return [
        {"id": c["id"], "name": c["name"], "legs": c["legs"], "created_at": c["created_at"]}
        for c in combinations.values()
    ]


@app.get("/api/combinations/{combo_id}/data")
async def get_combination_data(combo_id: str):
    if combo_id not in combinations:
        raise HTTPException(status_code=404, detail="Combination not found")

    combo = combinations[combo_id]
    legs = combo["legs"]

    merged = None

    for i, leg in enumerate(legs):
        ds = datasets[leg["dataset_id"]]
        df = ds["dataframe"].copy()
        dc = ds["date_column"]

        if dc is None:
            raise HTTPException(status_code=400, detail="Dataset must have a date column")

        col_name = f"leg_{i}_{leg['column']}"
        leg_df = df[[dc, leg["column"]]].rename(columns={leg["column"]: col_name, dc: "date"})
        leg_df["date"] = pd.to_datetime(leg_df["date"])

        if merged is None:
            merged = leg_df
        else:
            merged = pd.merge(merged, leg_df, on="date", how="inner")

    if merged is None or merged.empty:
        return {"combination_id": combo_id, "data": [], "stats": {}}

    merged["value"] = 0.0
    for i, leg in enumerate(legs):
        col_name = f"leg_{i}_{leg['column']}"
        merged["value"] += merged[col_name] * leg["weight"]

    records = []
    for _, row in merged.iterrows():
        record = {"date": row["date"].isoformat(), "value": float(row["value"])}
        for i, leg in enumerate(legs):
            col_name = f"leg_{i}_{leg['column']}"
            record[col_name] = float(row[col_name])
        records.append(record)

    values = merged["value"].dropna()
    stats = {
        "mean": float(values.mean()),
        "std": float(values.std()),
        "min": float(values.min()),
        "max": float(values.max()),
        "current": float(values.iloc[-1]) if len(values) > 0 else None,
        "count": int(len(values)),
    }

    return {"combination_id": combo_id, "name": combo["name"], "data": records, "stats": stats}


@app.delete("/api/combinations/{combo_id}")
async def delete_combination(combo_id: str):
    if combo_id not in combinations:
        raise HTTPException(status_code=404, detail="Combination not found")
    del combinations[combo_id]
    return {"status": "deleted"}


# --- Signal Generators ---

def compute_signal(series: pd.Series, signal_config: SignalConfig) -> pd.Series:
    """Compute trading signals: 1 = long, -1 = short, 0 = flat."""
    sig_type = signal_config.signal_type
    params = signal_config.params

    if sig_type == "ma_crossover":
        fast = int(params.get("fast_period", 10))
        slow = int(params.get("slow_period", 30))
        ma_type = params.get("ma_type", "sma")

        if ma_type == "ema":
            fast_ma = series.ewm(span=fast).mean()
            slow_ma = series.ewm(span=slow).mean()
        else:
            fast_ma = series.rolling(fast).mean()
            slow_ma = series.rolling(slow).mean()

        signal = pd.Series(0.0, index=series.index)
        signal[fast_ma > slow_ma] = 1.0
        signal[fast_ma < slow_ma] = -1.0
        return signal

    elif sig_type == "zscore":
        lookback = int(params.get("lookback", 20))
        entry_z = float(params.get("entry_threshold", 2.0))
        exit_z = float(params.get("exit_threshold", 0.5))

        rolling_mean = series.rolling(lookback).mean()
        rolling_std = series.rolling(lookback).std()
        zscore = (series - rolling_mean) / rolling_std

        signal = pd.Series(0.0, index=series.index)
        signal[zscore < -entry_z] = 1.0
        signal[zscore > entry_z] = -1.0
        for i in range(1, len(signal)):
            if signal.iloc[i] == 0:
                prev = signal.iloc[i - 1]
                if prev != 0 and abs(zscore.iloc[i]) > exit_z:
                    signal.iloc[i] = prev
        return signal

    elif sig_type == "rsi":
        period = int(params.get("period", 14))
        overbought = float(params.get("overbought", 70))
        oversold = float(params.get("oversold", 30))

        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        signal = pd.Series(0.0, index=series.index)
        signal[rsi < oversold] = 1.0
        signal[rsi > overbought] = -1.0

        for i in range(1, len(signal)):
            if signal.iloc[i] == 0:
                signal.iloc[i] = signal.iloc[i - 1]
        return signal

    elif sig_type == "bollinger":
        period = int(params.get("period", 20))
        num_std = float(params.get("num_std", 2.0))

        ma = series.rolling(period).mean()
        std = series.rolling(period).std()
        upper = ma + num_std * std
        lower = ma - num_std * std

        signal = pd.Series(0.0, index=series.index)
        signal[series < lower] = 1.0
        signal[series > upper] = -1.0

        for i in range(1, len(signal)):
            if signal.iloc[i] == 0:
                prev = signal.iloc[i - 1]
                if prev == 1.0 and series.iloc[i] < ma.iloc[i]:
                    signal.iloc[i] = 1.0
                elif prev == -1.0 and series.iloc[i] > ma.iloc[i]:
                    signal.iloc[i] = -1.0
        return signal

    elif sig_type == "threshold":
        buy_below = params.get("buy_below", None)
        sell_above = params.get("sell_above", None)

        signal = pd.Series(0.0, index=series.index)
        if buy_below is not None:
            signal[series < float(buy_below)] = 1.0
        if sell_above is not None:
            signal[series > float(sell_above)] = -1.0

        for i in range(1, len(signal)):
            if signal.iloc[i] == 0:
                signal.iloc[i] = signal.iloc[i - 1]
        return signal

    else:
        raise HTTPException(status_code=400, detail=f"Unknown signal type: {sig_type}")


# --- Backtest Endpoint ---

@app.post("/api/backtest")
async def run_backtest(req: BacktestRequest):
    if req.combination_id not in combinations:
        raise HTTPException(status_code=404, detail="Combination not found")

    combo = combinations[req.combination_id]
    legs = combo["legs"]

    merged = None
    for i, leg in enumerate(legs):
        ds = datasets[leg["dataset_id"]]
        df = ds["dataframe"].copy()
        dc = ds["date_column"]
        if dc is None:
            raise HTTPException(status_code=400, detail="Dataset must have a date column")

        col_name = f"leg_{i}_{leg['column']}"
        leg_df = df[[dc, leg["column"]]].rename(columns={leg["column"]: col_name, dc: "date"})
        leg_df["date"] = pd.to_datetime(leg_df["date"])

        if merged is None:
            merged = leg_df
        else:
            merged = pd.merge(merged, leg_df, on="date", how="inner")

    if merged is None or merged.empty:
        raise HTTPException(status_code=400, detail="No data available for this combination")

    merged["value"] = 0.0
    for i, leg in enumerate(legs):
        col_name = f"leg_{i}_{leg['column']}"
        merged["value"] += merged[col_name] * leg["weight"]

    merged = merged.sort_values("date").reset_index(drop=True)
    series = merged["value"]

    signal = compute_signal(series, req.signal)

    position = 0.0
    pnl = []
    cumulative_pnl = 0.0
    trades = []
    equity_curve = []
    entry_price = 0.0

    for i in range(1, len(merged)):
        date = merged["date"].iloc[i]
        price = series.iloc[i]
        prev_price = series.iloc[i - 1]
        target_pos = signal.iloc[i] * req.position_size

        if pd.isna(target_pos):
            target_pos = 0.0

        daily_pnl = position * (price - prev_price)

        hit_stop = False
        if position != 0 and entry_price != 0:
            unrealized = position * (price - entry_price)
            if req.stop_loss is not None and unrealized < -abs(req.stop_loss):
                target_pos = 0.0
                hit_stop = True
            if req.take_profit is not None and unrealized > abs(req.take_profit):
                target_pos = 0.0
                hit_stop = True

        trade_size = target_pos - position
        trade_cost = abs(trade_size) * req.transaction_cost

        if trade_size != 0:
            trades.append({
                "date": date.isoformat() if hasattr(date, "isoformat") else str(date),
                "price": float(price),
                "size": float(trade_size),
                "direction": "BUY" if trade_size > 0 else "SELL",
                "cost": float(trade_cost),
                "reason": "stop/tp" if hit_stop else "signal",
            })
            entry_price = price if target_pos != 0 else 0.0

        cumulative_pnl += daily_pnl - trade_cost
        pnl.append(daily_pnl - trade_cost)

        equity_curve.append({
            "date": date.isoformat() if hasattr(date, "isoformat") else str(date),
            "pnl": float(daily_pnl - trade_cost),
            "cumulative_pnl": float(cumulative_pnl),
            "position": float(target_pos),
            "price": float(price),
            "signal": float(signal.iloc[i]) if not pd.isna(signal.iloc[i]) else 0,
        })

        position = target_pos

    pnl_series = pd.Series(pnl)
    total_pnl = float(pnl_series.sum())
    num_trades = len(trades)

    if len(pnl_series) > 1 and pnl_series.std() > 0:
        sharpe = float(pnl_series.mean() / pnl_series.std() * np.sqrt(252))
    else:
        sharpe = 0.0

    cum_pnl = pnl_series.cumsum()
    running_max = cum_pnl.cummax()
    drawdown = cum_pnl - running_max
    max_drawdown = float(drawdown.min()) if len(drawdown) > 0 else 0.0

    winning_days = int((pnl_series > 0).sum())
    losing_days = int((pnl_series < 0).sum())
    win_rate = float(winning_days / (winning_days + losing_days) * 100) if (winning_days + losing_days) > 0 else 0.0

    avg_win = float(pnl_series[pnl_series > 0].mean()) if winning_days > 0 else 0.0
    avg_loss = float(pnl_series[pnl_series < 0].mean()) if losing_days > 0 else 0.0
    profit_factor = float(abs(avg_win * winning_days / (avg_loss * losing_days))) if losing_days > 0 and avg_loss != 0 else 0.0

    downside = pnl_series[pnl_series < 0]
    if len(downside) > 1 and downside.std() > 0:
        sortino = float(pnl_series.mean() / downside.std() * np.sqrt(252))
    else:
        sortino = 0.0

    calmar = float(total_pnl / abs(max_drawdown)) if max_drawdown != 0 else 0.0

    metrics = {
        "total_pnl": total_pnl,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "num_trades": num_trades,
        "winning_days": winning_days,
        "losing_days": losing_days,
        "avg_daily_pnl": float(pnl_series.mean()) if len(pnl_series) > 0 else 0.0,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "total_transaction_costs": float(sum(t["cost"] for t in trades)),
    }

    backtest_id = str(uuid.uuid4())[:8]
    backtests[backtest_id] = {
        "id": backtest_id,
        "name": req.name,
        "combination_id": req.combination_id,
        "combination_name": combo["name"],
        "signal": req.signal.model_dump(),
        "metrics": metrics,
        "equity_curve": equity_curve,
        "trades": trades,
        "created_at": datetime.utcnow().isoformat(),
    }

    return {
        "id": backtest_id,
        "name": req.name,
        "combination_name": combo["name"],
        "metrics": metrics,
        "equity_curve": equity_curve,
        "trades": trades,
    }


@app.get("/api/backtests")
async def list_backtests():
    return [
        {
            "id": b["id"],
            "name": b["name"],
            "combination_name": b["combination_name"],
            "metrics": b["metrics"],
            "created_at": b["created_at"],
        }
        for b in backtests.values()
    ]


@app.get("/api/backtests/{backtest_id}")
async def get_backtest(backtest_id: str):
    if backtest_id not in backtests:
        raise HTTPException(status_code=404, detail="Backtest not found")
    b = backtests[backtest_id]
    return {
        "id": b["id"],
        "name": b["name"],
        "combination_name": b["combination_name"],
        "signal": b["signal"],
        "metrics": b["metrics"],
        "equity_curve": b["equity_curve"],
        "trades": b["trades"],
    }


@app.delete("/api/backtests/{backtest_id}")
async def delete_backtest(backtest_id: str):
    if backtest_id not in backtests:
        raise HTTPException(status_code=404, detail="Backtest not found")
    del backtests[backtest_id]
    return {"status": "deleted"}


# ============================
# MARKET OVERVIEW
# ============================

@app.get("/api/datasets/{dataset_id}/market-overview")
async def get_market_overview(dataset_id: str):
    """Comprehensive market overview with stats, column detection, correlations."""
    if dataset_id not in datasets:
        raise HTTPException(status_code=404, detail="Dataset not found")

    d = datasets[dataset_id]
    df = d["dataframe"].copy()
    date_col = d["date_column"]
    numeric_cols = d["numeric_columns"]

    # Auto-detect column types
    price_cols = []
    volume_cols = []
    oi_cols = []
    other_cols = []

    for col in numeric_cols:
        col_lower = col.lower()
        if any(kw in col_lower for kw in ["oi", "open_interest", "openinterest"]):
            oi_cols.append(col)
        elif any(kw in col_lower for kw in ["vol", "volume"]):
            volume_cols.append(col)
        else:
            price_cols.append(col)

    # Per-column statistics
    column_stats = {}
    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) == 0:
            continue

        last_val = float(series.iloc[-1])
        prev_val = float(series.iloc[-2]) if len(series) > 1 else last_val
        change = last_val - prev_val
        change_pct = (change / prev_val * 100) if prev_val != 0 else 0

        returns = series.pct_change().dropna()
        vol_20d = float(returns.tail(20).std() * np.sqrt(252) * 100) if len(returns) >= 20 else 0

        ma_10 = float(series.rolling(10).mean().iloc[-1]) if len(series) >= 10 else None
        ma_20 = float(series.rolling(20).mean().iloc[-1]) if len(series) >= 20 else None
        ma_50 = float(series.rolling(50).mean().iloc[-1]) if len(series) >= 50 else None
        ma_200 = float(series.rolling(200).mean().iloc[-1]) if len(series) >= 200 else None

        column_stats[col] = {
            "last": last_val,
            "prev_close": prev_val,
            "change": float(change),
            "change_pct": float(change_pct),
            "high": float(series.max()),
            "low": float(series.min()),
            "mean": float(series.mean()),
            "std": float(series.std()),
            "volatility_20d": vol_20d,
            "ma_10": ma_10,
            "ma_20": ma_20,
            "ma_50": ma_50,
            "ma_200": ma_200,
            "percentile": float((series < last_val).mean() * 100),
        }

    # Correlation matrix
    correlations = {}
    if len(numeric_cols) > 1:
        corr_matrix = df[numeric_cols].corr()
        for i, col1 in enumerate(numeric_cols):
            for j, col2 in enumerate(numeric_cols):
                if i < j:
                    val = corr_matrix.loc[col1, col2]
                    correlations[f"{col1}_vs_{col2}"] = round(float(val), 4) if not pd.isna(val) else 0

    # Date range
    date_range = None
    if date_col:
        dates = pd.to_datetime(df[date_col])
        date_range = {
            "start": dates.min().isoformat(),
            "end": dates.max().isoformat(),
            "trading_days": int(len(dates)),
        }

    # Prepare chart data
    records = []
    for _, row in df.iterrows():
        record = {}
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                record[col] = None
            elif isinstance(val, (pd.Timestamp, datetime)):
                record[col] = val.isoformat()
            elif isinstance(val, (np.integer,)):
                record[col] = int(val)
            elif isinstance(val, (np.floating,)):
                record[col] = float(val)
            else:
                record[col] = val
        records.append(record)

    return {
        "dataset_id": dataset_id,
        "name": d["name"],
        "date_column": date_col,
        "columns": d["columns"],
        "numeric_columns": numeric_cols,
        "row_count": d["row_count"],
        "date_range": date_range,
        "price_columns": price_cols,
        "volume_columns": volume_cols,
        "oi_columns": oi_cols,
        "other_columns": other_cols,
        "column_stats": column_stats,
        "correlations": correlations,
        "data": records,
    }


# ============================
# OI / VOLUME ANALYSIS
# ============================

@app.get("/api/datasets/{dataset_id}/oi-volume")
async def get_oi_volume_analysis(dataset_id: str):
    """Analyze open interest and volume columns from a dataset."""
    if dataset_id not in datasets:
        raise HTTPException(status_code=404, detail="Dataset not found")

    d = datasets[dataset_id]
    df = d["dataframe"].copy()
    dc = d["date_column"]
    if dc is None:
        raise HTTPException(status_code=400, detail="Dataset must have a date column")

    # Detect OI and Volume columns (case-insensitive matching)
    oi_cols = [c for c in d["numeric_columns"] if any(k in c.lower() for k in ["oi", "open_interest", "openinterest", "open interest"])]
    vol_cols = [c for c in d["numeric_columns"] if any(k in c.lower() for k in ["vol", "volume"])]
    price_cols = [c for c in d["numeric_columns"] if c not in oi_cols and c not in vol_cols]

    # If no OI/Volume columns detected, return all numeric columns for the user to pick
    all_numeric = d["numeric_columns"]

    # Compute rolling stats for each detected column
    analysis = {}
    for col in all_numeric:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        ma_20 = s.rolling(20).mean()
        ma_50 = s.rolling(50).mean()
        pct_change = s.pct_change()

        analysis[col] = {
            "current": float(s.iloc[-1]),
            "mean": float(s.mean()),
            "std": float(s.std()),
            "min": float(s.min()),
            "max": float(s.max()),
            "ma_20_current": float(ma_20.iloc[-1]) if not pd.isna(ma_20.iloc[-1]) else None,
            "ma_50_current": float(ma_50.iloc[-1]) if not pd.isna(ma_50.iloc[-1]) else None,
            "avg_daily_change_pct": float(pct_change.mean() * 100) if len(pct_change.dropna()) > 0 else 0,
        }

    # Build time series data
    records = []
    for _, row in df.iterrows():
        record = {"date": row[dc].isoformat() if hasattr(row[dc], "isoformat") else str(row[dc])}
        for col in all_numeric:
            val = row[col]
            record[col] = float(val) if not pd.isna(val) else None
        records.append(record)

    # Compute OI-Price and Volume-Price correlations
    correlations = {}
    for oi_col in oi_cols:
        for pc in price_cols:
            if oi_col in df.columns and pc in df.columns:
                corr_val = df[oi_col].corr(df[pc])
                correlations[f"{oi_col} vs {pc}"] = float(corr_val) if not pd.isna(corr_val) else 0
    for vol_col in vol_cols:
        for pc in price_cols:
            if vol_col in df.columns and pc in df.columns:
                corr_val = df[vol_col].corr(df[pc])
                correlations[f"{vol_col} vs {pc}"] = float(corr_val) if not pd.isna(corr_val) else 0

    # Volume/OI change analysis
    changes = {}
    for col in oi_cols + vol_cols:
        s = df[col].dropna()
        if len(s) < 2:
            continue
        daily_change = s.diff()
        changes[col] = {
            "avg_daily_change": float(daily_change.mean()),
            "max_increase": float(daily_change.max()),
            "max_decrease": float(daily_change.min()),
            "days_increasing": int((daily_change > 0).sum()),
            "days_decreasing": int((daily_change < 0).sum()),
        }

    return {
        "dataset_id": dataset_id,
        "name": d["name"],
        "detected_oi_columns": oi_cols,
        "detected_volume_columns": vol_cols,
        "detected_price_columns": price_cols,
        "all_numeric_columns": all_numeric,
        "column_stats": analysis,
        "correlations": correlations,
        "change_analysis": changes,
        "data": records,
    }


# ============================
# HISTORICAL PATTERN / TREND
# ============================

@app.get("/api/datasets/{dataset_id}/patterns")
async def get_historical_patterns(dataset_id: str, column: str):
    """Analyze historical patterns: seasonality, trend, autocorrelation."""
    if dataset_id not in datasets:
        raise HTTPException(status_code=404, detail="Dataset not found")

    d = datasets[dataset_id]
    df = d["dataframe"].copy()
    dc = d["date_column"]
    if dc is None:
        raise HTTPException(status_code=400, detail="Dataset must have a date column")
    if column not in d["numeric_columns"]:
        raise HTTPException(status_code=400, detail=f"Column {column} not found or not numeric")

    df["_date"] = pd.to_datetime(df[dc])
    df = df.sort_values("_date").reset_index(drop=True)
    series = df[column].dropna()

    # --- Trend Analysis ---
    # Linear trend
    x = np.arange(len(series))
    if len(x) > 1:
        coeffs = np.polyfit(x, series.values, 1)
        trend_slope = float(coeffs[0])
        trend_intercept = float(coeffs[1])
        trend_line = np.polyval(coeffs, x)
    else:
        trend_slope = 0.0
        trend_intercept = 0.0
        trend_line = series.values

    # Moving averages for trend
    ma_10 = series.rolling(10).mean()
    ma_20 = series.rolling(20).mean()
    ma_50 = series.rolling(50).mean()
    ma_100 = series.rolling(100).mean()

    # --- Seasonality (monthly averages) ---
    df["_month"] = df["_date"].dt.month
    df["_year"] = df["_date"].dt.year
    monthly_avg = df.groupby("_month")[column].mean()
    monthly_std = df.groupby("_month")[column].std()

    seasonality = []
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for m in range(1, 13):
        if m in monthly_avg.index:
            seasonality.append({
                "month": m,
                "month_name": month_names[m - 1],
                "avg": float(monthly_avg[m]),
                "std": float(monthly_std[m]) if m in monthly_std.index and not pd.isna(monthly_std[m]) else 0,
            })

    # --- Year-over-year patterns ---
    yearly_data = {}
    for year in sorted(df["_year"].unique()):
        year_df = df[df["_year"] == year].copy()
        year_df["_doy"] = year_df["_date"].dt.dayofyear
        yearly_data[int(year)] = [
            {"day_of_year": int(row["_doy"]), "value": float(row[column])}
            for _, row in year_df.iterrows()
            if not pd.isna(row[column])
        ]

    # --- Autocorrelation ---
    autocorr = []
    max_lag = min(60, len(series) // 4)
    for lag in range(1, max_lag + 1):
        ac = float(series.autocorr(lag))
        autocorr.append({"lag": lag, "autocorrelation": ac if not pd.isna(ac) else 0})

    # --- Returns distribution ---
    returns = series.pct_change().dropna()
    if len(returns) > 0:
        returns_stats = {
            "mean": float(returns.mean()),
            "std": float(returns.std()),
            "skew": float(returns.skew()),
            "kurtosis": float(returns.kurtosis()),
            "min": float(returns.min()),
            "max": float(returns.max()),
        }
        # Histogram bins
        hist_vals, hist_edges = np.histogram(returns.values, bins=30)
        returns_hist = [
            {"bin_start": float(hist_edges[i]), "bin_end": float(hist_edges[i + 1]), "count": int(hist_vals[i])}
            for i in range(len(hist_vals))
        ]
    else:
        returns_stats = {}
        returns_hist = []

    # Build trend time series
    trend_data = []
    for i, (_, row) in enumerate(df.iterrows()):
        if pd.isna(row[column]):
            continue
        entry = {
            "date": row["_date"].isoformat(),
            "value": float(row[column]),
            "trend": float(trend_line[i]) if i < len(trend_line) else None,
            "ma_10": float(ma_10.iloc[i]) if not pd.isna(ma_10.iloc[i]) else None,
            "ma_20": float(ma_20.iloc[i]) if not pd.isna(ma_20.iloc[i]) else None,
            "ma_50": float(ma_50.iloc[i]) if not pd.isna(ma_50.iloc[i]) else None,
            "ma_100": float(ma_100.iloc[i]) if not pd.isna(ma_100.iloc[i]) else None,
        }
        trend_data.append(entry)

    return {
        "dataset_id": dataset_id,
        "column": column,
        "trend": {
            "slope": trend_slope,
            "intercept": trend_intercept,
            "direction": "upward" if trend_slope > 0 else "downward",
            "slope_annualized": trend_slope * 252,
        },
        "seasonality": seasonality,
        "yearly_data": yearly_data,
        "autocorrelation": autocorr,
        "returns_stats": returns_stats,
        "returns_histogram": returns_hist,
        "trend_data": trend_data,
    }


# ============================
# SUPPLY / DEMAND BALANCES (PADD Excel)
# ============================

balance_datasets: dict[str, dict] = {}


def _parse_padd_excel(content: bytes, filename: str) -> dict:
    """Parse PADD-style gasoline balances Excel file.
    Structure: rows = metrics, columns = monthly dates.
    PADDs separated by rows containing 'PADD X - Net Production'.
    Date header rows appear before each PADD section (or before PADD 2/3).
    """
    df = pd.read_excel(io.BytesIO(content), header=None)
    n_rows, n_cols = df.shape

    # 1) Find PADD boundary rows (rows whose col-A text starts with "PADD X -")
    padd_boundaries: list[tuple[int, str, int]] = []  # (row_idx, padd_name, padd_num)
    for i in range(n_rows):
        val = str(df.iloc[i, 0]).strip().replace("\xa0", " ") if pd.notna(df.iloc[i, 0]) else ""
        if val.upper().startswith("PADD") and "Net Production" in val:
            # Extract PADD number
            parts = val.split("-")[0].strip().split()
            padd_num = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            padd_name = f"PADD {padd_num}"
            padd_boundaries.append((i, padd_name, padd_num))

    if not padd_boundaries:
        raise ValueError("No PADD sections found in the file")

    # 2) Find date header rows: rows where col D+ contain datetime values
    date_rows: list[int] = []
    for i in range(n_rows):
        v = df.iloc[i, 3] if n_cols > 3 else None
        if isinstance(v, datetime):
            date_rows.append(i)

    # Extract dates from the first date header row found
    dates: list[datetime] = []
    date_row_idx = date_rows[0] if date_rows else -1
    if date_row_idx >= 0:
        for c in range(3, n_cols):
            v = df.iloc[date_row_idx, c]
            if isinstance(v, datetime):
                dates.append(v)
            elif pd.notna(v):
                try:
                    dates.append(pd.to_datetime(v))
                except Exception:
                    pass

    # If no dates found from header row, try to infer from PADD 1 data
    if not dates:
        raise ValueError("Could not find date headers in the file")

    n_dates = len(dates)

    # 3) Parse each PADD section
    padds: dict[str, dict] = {}
    for idx, (start_row, padd_name, padd_num) in enumerate(padd_boundaries):
        # End row is either next PADD boundary or end of file
        if idx + 1 < len(padd_boundaries):
            end_row = padd_boundaries[idx + 1][0]
        else:
            end_row = n_rows

        metrics: list[dict] = []
        for r in range(start_row, end_row):
            label = str(df.iloc[r, 0]).strip().replace("\xa0", " ") if pd.notna(df.iloc[r, 0]) else ""
            if not label:
                continue
            # Skip date header rows
            if r in date_rows:
                continue

            # Clean label - remove PADD prefix for display
            display_label = label
            for prefix in [f"PADD {padd_num} - ", f"PADD {padd_num}  ", f"PADD {padd_num} ",
                           f"Midwest (PADD {padd_num}) "]:
                if display_label.startswith(prefix):
                    display_label = display_label[len(prefix):]
                    break

            # Extract values
            values: list[float | None] = []
            for c in range(3, 3 + n_dates):
                if c < n_cols:
                    v = df.iloc[r, c]
                    if pd.notna(v):
                        try:
                            values.append(float(v))
                        except (ValueError, TypeError):
                            values.append(None)
                    else:
                        values.append(None)
                else:
                    values.append(None)

            if any(v is not None for v in values):
                metrics.append({
                    "label": display_label,
                    "original_label": label,
                    "values": values,
                })

        padds[padd_name] = {
            "padd_num": padd_num,
            "metrics": metrics,
            "metric_names": [m["label"] for m in metrics],
        }

    return {
        "dates": [d.isoformat() for d in dates],
        "padds": padds,
        "padd_names": [pb[1] for pb in padd_boundaries],
    }


@app.post("/api/balances/upload")
async def upload_balance_dataset(file: UploadFile = File(...)):
    """Upload a PADD-style gasoline balances Excel or CSV file."""
    try:
        content = await file.read()
        fname = file.filename or "unnamed"

        if fname.lower().endswith((".xlsx", ".xls")):
            parsed = _parse_padd_excel(content, fname)
            dataset_id = str(uuid.uuid4())[:8]
            balance_datasets[dataset_id] = {
                "id": dataset_id,
                "name": fname,
                "type": "padd_excel",
                "dates": parsed["dates"],
                "padds": parsed["padds"],
                "padd_names": parsed["padd_names"],
                "uploaded_at": datetime.utcnow().isoformat(),
            }
            return {
                "id": dataset_id,
                "name": fname,
                "type": "padd_excel",
                "padd_names": parsed["padd_names"],
                "num_dates": len(parsed["dates"]),
                "date_range": {"start": parsed["dates"][0], "end": parsed["dates"][-1]} if parsed["dates"] else None,
            }
        else:
            # Fallback: CSV upload (old behavior)
            df = pd.read_csv(io.BytesIO(content))
            date_col = None
            for col in df.columns:
                if col.lower() in ["date", "dates", "timestamp", "time", "datetime"]:
                    date_col = col
                    break
            if date_col:
                df[date_col] = pd.to_datetime(df[date_col])
                df = df.sort_values(date_col).reset_index(drop=True)

            dataset_id = str(uuid.uuid4())[:8]
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            balance_datasets[dataset_id] = {
                "id": dataset_id,
                "name": fname,
                "type": "csv",
                "date_column": date_col,
                "columns": df.columns.tolist(),
                "numeric_columns": numeric_cols,
                "row_count": len(df),
                "uploaded_at": datetime.utcnow().isoformat(),
                "dataframe": df,
            }
            return {
                "id": dataset_id,
                "name": fname,
                "type": "csv",
                "columns": df.columns.tolist(),
                "row_count": len(df),
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")


@app.get("/api/balances")
async def list_balance_datasets():
    results = []
    for d in balance_datasets.values():
        item = {"id": d["id"], "name": d["name"], "type": d.get("type", "csv"), "uploaded_at": d.get("uploaded_at")}
        if d.get("type") == "padd_excel":
            item["padd_names"] = d["padd_names"]
            item["num_dates"] = len(d["dates"])
        results.append(item)
    return results


@app.get("/api/balances/{dataset_id}")
async def get_balance_dataset(dataset_id: str):
    if dataset_id not in balance_datasets:
        raise HTTPException(status_code=404, detail="Balance dataset not found")
    d = balance_datasets[dataset_id]

    if d.get("type") == "padd_excel":
        # Return PADD structure
        padd_data = {}
        for padd_name, padd_info in d["padds"].items():
            padd_data[padd_name] = {
                "padd_num": padd_info["padd_num"],
                "metric_names": padd_info["metric_names"],
                "metrics": [
                    {"label": m["label"], "values": m["values"]}
                    for m in padd_info["metrics"]
                ],
            }
        return {
            "id": d["id"],
            "name": d["name"],
            "type": "padd_excel",
            "dates": d["dates"],
            "padd_names": d["padd_names"],
            "padds": padd_data,
        }
    else:
        raise HTTPException(status_code=400, detail="Use CSV endpoint for non-PADD data")


@app.get("/api/balances/{dataset_id}/seasonal")
async def get_seasonal_data(dataset_id: str, padd: str, metric: str):
    """Get seasonal (year-over-year) data for a specific PADD metric."""
    if dataset_id not in balance_datasets:
        raise HTTPException(status_code=404, detail="Balance dataset not found")
    d = balance_datasets[dataset_id]
    if d.get("type") != "padd_excel":
        raise HTTPException(status_code=400, detail="Seasonal view only for PADD Excel data")

    if padd not in d["padds"]:
        raise HTTPException(status_code=404, detail=f"PADD '{padd}' not found")

    padd_info = d["padds"][padd]
    metric_data = None
    for m in padd_info["metrics"]:
        if m["label"] == metric:
            metric_data = m
            break
    if metric_data is None:
        raise HTTPException(status_code=404, detail=f"Metric '{metric}' not found in {padd}")

    dates = [datetime.fromisoformat(ds) for ds in d["dates"]]
    values = metric_data["values"]

    # Group by year, with month as x-axis
    yearly: dict[int, list[dict]] = {}
    for i, dt in enumerate(dates):
        year = dt.year
        month = dt.month
        val = values[i] if i < len(values) else None
        if year not in yearly:
            yearly[year] = []
        yearly[year].append({"month": month, "value": val})

    # Build seasonal chart data: each row = {month, month_name, year1: val, year2: val, ...}
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    years = sorted(yearly.keys())
    seasonal_data = []
    for m in range(1, 13):
        row: dict = {"month": m, "month_name": month_names[m - 1]}
        for yr in years:
            yr_data = yearly[yr]
            val = None
            for entry in yr_data:
                if entry["month"] == m:
                    val = entry["value"]
                    break
            row[str(yr)] = val
        seasonal_data.append(row)

    return {
        "dataset_id": dataset_id,
        "padd": padd,
        "metric": metric,
        "years": [str(y) for y in years],
        "seasonal_data": seasonal_data,
    }


@app.get("/api/balances/{dataset_id}/cross-padd")
async def get_cross_padd_data(dataset_id: str, metric: str = Query(...)):
    """Get the same metric across all PADDs for comparison (seasonal overlay)."""
    if dataset_id not in balance_datasets:
        raise HTTPException(status_code=404, detail="Balance dataset not found")
    d = balance_datasets[dataset_id]
    if d.get("type") != "padd_excel":
        raise HTTPException(status_code=400, detail="Cross-PADD only for PADD Excel data")

    dates = [datetime.fromisoformat(ds) for ds in d["dates"]]
    result_padds = {}

    for padd_name, padd_info in d["padds"].items():
        # Find the metric (try exact match first, then substring)
        metric_data = None
        for m in padd_info["metrics"]:
            if m["label"] == metric or metric.lower() in m["label"].lower():
                metric_data = m
                break
        if metric_data is None:
            continue

        values = metric_data["values"]
        # Group by year
        yearly: dict[int, list] = {}
        for i, dt in enumerate(dates):
            val = values[i] if i < len(values) else None
            if dt.year not in yearly:
                yearly[dt.year] = []
            yearly[dt.year].append({"month": dt.month, "value": val})

        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        years = sorted(yearly.keys())
        seasonal_data = []
        for m_num in range(1, 13):
            row: dict = {"month": m_num, "month_name": month_names[m_num - 1]}
            for yr in years:
                val = None
                for entry in yearly[yr]:
                    if entry["month"] == m_num:
                        val = entry["value"]
                        break
                row[str(yr)] = val
            seasonal_data.append(row)

        result_padds[padd_name] = {
            "years": [str(y) for y in years],
            "seasonal_data": seasonal_data,
            "metric_label": metric_data["label"],
        }

    return {
        "dataset_id": dataset_id,
        "metric": metric,
        "padds": result_padds,
    }


@app.get("/api/balances/{dataset_id}/yoy-change")
async def get_yoy_change(dataset_id: str, padd: str = Query(...), metric: str = Query(...)):
    """Get year-over-year percentage change for a PADD metric."""
    if dataset_id not in balance_datasets:
        raise HTTPException(status_code=404, detail="Balance dataset not found")
    d = balance_datasets[dataset_id]
    if d.get("type") != "padd_excel":
        raise HTTPException(status_code=400, detail="YoY only for PADD Excel data")
    if padd not in d["padds"]:
        raise HTTPException(status_code=404, detail=f"PADD '{padd}' not found")

    padd_info = d["padds"][padd]
    metric_data = None
    for m in padd_info["metrics"]:
        if m["label"] == metric:
            metric_data = m
            break
    if metric_data is None:
        raise HTTPException(status_code=404, detail=f"Metric '{metric}' not found in {padd}")

    dates = [datetime.fromisoformat(ds) for ds in d["dates"]]
    values = metric_data["values"]

    # Build monthly dict: {(year, month): value}
    monthly: dict[tuple[int, int], float | None] = {}
    for i, dt in enumerate(dates):
        monthly[(dt.year, dt.month)] = values[i] if i < len(values) else None

    years = sorted(set(dt.year for dt in dates))
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    yoy_data = []
    for m_num in range(1, 13):
        row: dict = {"month": m_num, "month_name": month_names[m_num - 1]}
        for yr in years:
            curr = monthly.get((yr, m_num))
            prev = monthly.get((yr - 1, m_num))
            if curr is not None and prev is not None and prev != 0:
                row[str(yr)] = round((curr - prev) / abs(prev) * 100, 2)
            else:
                row[str(yr)] = None
        yoy_data.append(row)

    # Skip first year since no previous year to compare
    display_years = [str(y) for y in years if y > years[0]]

    return {
        "dataset_id": dataset_id,
        "padd": padd,
        "metric": metric,
        "years": display_years,
        "yoy_data": yoy_data,
    }


@app.get("/api/balances/{dataset_id}/range-bands")
async def get_range_bands(dataset_id: str, padd: str = Query(...), metric: str = Query(...),
                          band_years: int = Query(default=5)):
    """Get min/max/avg range bands for a PADD metric with current year highlighted."""
    if dataset_id not in balance_datasets:
        raise HTTPException(status_code=404, detail="Balance dataset not found")
    d = balance_datasets[dataset_id]
    if d.get("type") != "padd_excel":
        raise HTTPException(status_code=400, detail="Range bands only for PADD Excel data")
    if padd not in d["padds"]:
        raise HTTPException(status_code=404, detail=f"PADD '{padd}' not found")

    padd_info = d["padds"][padd]
    metric_data = None
    for m in padd_info["metrics"]:
        if m["label"] == metric:
            metric_data = m
            break
    if metric_data is None:
        raise HTTPException(status_code=404, detail=f"Metric '{metric}' not found in {padd}")

    dates = [datetime.fromisoformat(ds) for ds in d["dates"]]
    values = metric_data["values"]

    # Group by year
    yearly: dict[int, dict[int, float | None]] = {}
    for i, dt in enumerate(dates):
        if dt.year not in yearly:
            yearly[dt.year] = {}
        yearly[dt.year][dt.month] = values[i] if i < len(values) else None

    years = sorted(yearly.keys())
    current_year = years[-1] if years else 0
    prev_year = years[-2] if len(years) >= 2 else None
    # Use last N years for range bands (excluding current year)
    band_year_list = [y for y in years if y < current_year][-band_years:]

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    band_data = []
    for m_num in range(1, 13):
        vals = []
        for yr in band_year_list:
            v = yearly.get(yr, {}).get(m_num)
            if v is not None:
                vals.append(v)

        row: dict = {
            "month": m_num,
            "month_name": month_names[m_num - 1],
            "min": min(vals) if vals else None,
            "max": max(vals) if vals else None,
            "avg": round(sum(vals) / len(vals), 2) if vals else None,
            "current": yearly.get(current_year, {}).get(m_num),
        }
        if prev_year is not None:
            row["prev_year"] = yearly.get(prev_year, {}).get(m_num)
        band_data.append(row)

    return {
        "dataset_id": dataset_id,
        "padd": padd,
        "metric": metric,
        "current_year": current_year,
        "prev_year": prev_year,
        "band_years": band_year_list,
        "band_data": band_data,
    }


@app.get("/api/balances/{dataset_id}/correlation")
async def get_correlation(
    dataset_id: str,
    padd1: str = Query(...), metric1: str = Query(...),
    padd2: str = Query(...), metric2: str = Query(...),
):
    """Compute correlation between two PADD metrics."""
    if dataset_id not in balance_datasets:
        raise HTTPException(status_code=404, detail="Balance dataset not found")
    d = balance_datasets[dataset_id]
    if d.get("type") != "padd_excel":
        raise HTTPException(status_code=400, detail="Correlation only for PADD Excel data")

    def _get_values(padd_name: str, metric_name: str):
        if padd_name not in d["padds"]:
            raise HTTPException(status_code=404, detail=f"PADD '{padd_name}' not found")
        for m in d["padds"][padd_name]["metrics"]:
            if m["label"] == metric_name:
                return m["values"]
        raise HTTPException(status_code=404, detail=f"Metric '{metric_name}' not found in {padd_name}")

    vals1 = _get_values(padd1, metric1)
    vals2 = _get_values(padd2, metric2)
    dates = d["dates"]

    # Build paired data (only where both have values)
    scatter = []
    s1, s2 = [], []
    for i in range(min(len(vals1), len(vals2), len(dates))):
        v1, v2 = vals1[i], vals2[i]
        if v1 is not None and v2 is not None:
            scatter.append({"x": v1, "y": v2, "date": dates[i][:7]})
            s1.append(v1)
            s2.append(v2)

    if len(s1) < 3:
        return {
            "dataset_id": dataset_id,
            "series1": f"{padd1} - {metric1}",
            "series2": f"{padd2} - {metric2}",
            "r_squared": None,
            "correlation": None,
            "scatter": scatter,
            "rolling_corr": [],
        }

    arr1 = np.array(s1, dtype=float)
    arr2 = np.array(s2, dtype=float)
    corr = float(np.corrcoef(arr1, arr2)[0, 1])
    r_squared = round(corr ** 2, 4)

    # Rolling correlation (12-month window)
    window = min(12, len(s1) - 1)
    rolling_corr = []
    for i in range(window, len(s1)):
        w1 = arr1[i - window:i]
        w2 = arr2[i - window:i]
        if np.std(w1) > 0 and np.std(w2) > 0:
            rc = float(np.corrcoef(w1, w2)[0, 1])
        else:
            rc = None
        rolling_corr.append({"date": dates[i][:7] if i < len(dates) else "", "correlation": rc})

    # Linear regression for trend line
    slope, intercept = float(np.polyfit(arr1, arr2, 1)[0]), float(np.polyfit(arr1, arr2, 1)[1])

    return {
        "dataset_id": dataset_id,
        "series1": f"{padd1} - {metric1}",
        "series2": f"{padd2} - {metric2}",
        "correlation": round(corr, 4),
        "r_squared": r_squared,
        "scatter": scatter,
        "rolling_corr": rolling_corr,
        "regression": {"slope": round(slope, 4), "intercept": round(intercept, 2)},
        "stats": {
            "n": len(s1),
            "mean1": round(float(np.mean(arr1)), 2),
            "mean2": round(float(np.mean(arr2)), 2),
            "std1": round(float(np.std(arr1)), 2),
            "std2": round(float(np.std(arr2)), 2),
        }
    }


@app.delete("/api/balances/{dataset_id}")
async def delete_balance_dataset(dataset_id: str):
    if dataset_id not in balance_datasets:
        raise HTTPException(status_code=404, detail="Balance dataset not found")
    del balance_datasets[dataset_id]
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
# ═══  COT (Commitment of Traders) DATA
# ═══════════════════════════════════════════════════════════════════════════════

cot_data: dict = {}  # Single COT dataset

CATEGORY_MAP = {
    "Producers": "Producers",
    "Swap Dealers": "Swap Dealers",
    "Managed Money ": "Managed Money",
    "Managed Money": "Managed Money",
    "Other Reportables": "Other Reportables",
    "Sheet5": "Non-Reportable",
    "Non-Reportable": "Non-Reportable",
    "Non Reportables": "Non-Reportable",
}

# CO1/CO2 price/volume/OI data from COTnew
co_price_data: dict = {}  # {"CO1": [...], "CO2": [...]}


def _parse_cot_excel(content: bytes) -> dict:
    """Parse COT Excel with category sheets."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    categories = {}

    # Sheets to skip (price data, not COT categories)
    skip_sheets = {"CO1", "CO2"}
    for sheet_name in wb.sheetnames:
        if sheet_name.strip() in skip_sheets:
            continue
        cat_name = CATEGORY_MAP.get(sheet_name.strip(), sheet_name.strip())
        ws = wb[sheet_name]
        if ws.max_row < 2:
            continue

        headers = []
        for col in range(1, ws.max_column + 1):
            v = ws.cell(row=1, column=col).value
            headers.append(str(v).strip() if v else f"col_{col}")

        rows = []
        for row in range(2, ws.max_row + 1):
            date_val = ws.cell(row=row, column=1).value
            if date_val is None:
                continue
            if isinstance(date_val, datetime):
                date_str = date_val.strftime("%Y-%m-%d")
            else:
                try:
                    date_str = pd.to_datetime(str(date_val)).strftime("%Y-%m-%d")
                except Exception:
                    continue

            row_data = {"date": date_str}
            for ci in range(1, len(headers)):
                val = ws.cell(row=row, column=ci + 1).value
                if val is not None:
                    try:
                        row_data[headers[ci].lower().replace(" ", "_")] = float(val)
                    except (ValueError, TypeError):
                        row_data[headers[ci].lower().replace(" ", "_")] = None
                else:
                    row_data[headers[ci].lower().replace(" ", "_")] = None
            rows.append(row_data)

        rows.sort(key=lambda x: x["date"])

        # Normalize column names
        norm_rows = []
        for r in rows:
            nr = {"date": r["date"]}
            for k, v in r.items():
                if k == "date":
                    continue
                kl = k.lower()
                if "long" in kl and "net" not in kl:
                    nr["long"] = v
                elif "short" in kl:
                    nr["short"] = v
                elif "spreading" in kl or "spread" in kl:
                    nr["spreading"] = v
                elif "net" in kl or "last" in kl:
                    nr["net"] = v
            # Compute net if missing
            if "net" not in nr and nr.get("long") is not None and nr.get("short") is not None:
                nr["net"] = nr["long"] - nr["short"]
            norm_rows.append(nr)

        categories[cat_name] = {
            "data": norm_rows,
            "row_count": len(norm_rows),
            "has_spreading": any(r.get("spreading") is not None for r in norm_rows),
            "headers": headers,
        }

    wb.close()
    return categories


@app.post("/api/cot/upload")
async def upload_cot(file: UploadFile = File(...)):
    """Upload COT Excel data."""
    try:
        content = await file.read()
        parsed = _parse_cot_excel(content)
        cot_data.clear()
        cot_data["categories"] = parsed
        cot_data["filename"] = file.filename
        cot_data["uploaded_at"] = datetime.utcnow().isoformat()
        cat_list = list(parsed.keys())
        total_rows = sum(c["row_count"] for c in parsed.values())
        return {
            "status": "ok",
            "categories": cat_list,
            "total_rows": total_rows,
            "filename": file.filename,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/cot/summary")
async def cot_summary():
    """Get COT data summary and latest snapshot."""
    if not cot_data.get("categories"):
        raise HTTPException(status_code=404, detail="No COT data uploaded")

    categories = cot_data["categories"]
    summary = []

    for cat_name, cat_info in categories.items():
        data = cat_info["data"]
        if not data:
            continue
        latest = data[-1]
        prev = data[-2] if len(data) > 1 else latest

        long_val = latest.get("long", 0) or 0
        short_val = latest.get("short", 0) or 0
        net_val = latest.get("net", 0) or 0
        spreading_val = latest.get("spreading")

        prev_long = prev.get("long", 0) or 0
        prev_short = prev.get("short", 0) or 0
        prev_net = prev.get("net", 0) or 0

        # Historical percentile for net position
        net_series = [r.get("net", 0) or 0 for r in data]
        net_arr = np.array(net_series)
        percentile = float(np.sum(net_arr <= net_val) / len(net_arr) * 100) if len(net_arr) > 0 else 50

        # 4-week and 12-week averages
        avg_4w = float(np.mean(net_arr[-4:])) if len(net_arr) >= 4 else float(np.mean(net_arr))
        avg_12w = float(np.mean(net_arr[-12:])) if len(net_arr) >= 12 else float(np.mean(net_arr))

        cat_summary = {
            "category": cat_name,
            "latest_date": latest["date"],
            "long": long_val,
            "short": short_val,
            "net": net_val,
            "long_chg": long_val - prev_long,
            "short_chg": short_val - prev_short,
            "net_chg": net_val - prev_net,
            "percentile": round(percentile, 1),
            "avg_4w": round(avg_4w, 0),
            "avg_12w": round(avg_12w, 0),
            "data_points": len(data),
            "has_spreading": cat_info["has_spreading"],
        }
        if spreading_val is not None:
            cat_summary["spreading"] = spreading_val
        summary.append(cat_summary)

    return {
        "filename": cot_data.get("filename"),
        "categories": [s["category"] for s in summary],
        "summary": summary,
    }


@app.get("/api/cot/category/{category}")
async def cot_category_data(category: str):
    """Get full time series for a specific COT category."""
    if not cot_data.get("categories"):
        raise HTTPException(status_code=404, detail="No COT data uploaded")

    cat_info = None
    for k, v in cot_data["categories"].items():
        if k.lower().replace(" ", "") == category.lower().replace(" ", ""):
            cat_info = v
            category = k
            break
    if cat_info is None:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found")

    data = cat_info["data"]
    net_series = np.array([r.get("net", 0) or 0 for r in data], dtype=float)
    long_series = np.array([r.get("long", 0) or 0 for r in data], dtype=float)
    short_series = np.array([r.get("short", 0) or 0 for r in data], dtype=float)

    # Week-over-week changes
    net_chg = np.diff(net_series, prepend=net_series[0])
    long_chg = np.diff(long_series, prepend=long_series[0])
    short_chg = np.diff(short_series, prepend=short_series[0])

    # Rolling stats
    windows = {"4w": 4, "12w": 12, "26w": 26, "52w": 52}
    rolling_stats = {}
    for wname, wsize in windows.items():
        if len(net_series) >= wsize:
            rolling_avg = []
            rolling_std = []
            for i in range(len(net_series)):
                if i < wsize - 1:
                    rolling_avg.append(None)
                    rolling_std.append(None)
                else:
                    w = net_series[i - wsize + 1:i + 1]
                    rolling_avg.append(round(float(np.mean(w)), 0))
                    rolling_std.append(round(float(np.std(w)), 0))
            rolling_stats[wname] = {"avg": rolling_avg, "std": rolling_std}

    # Historical percentile at each point
    percentiles = []
    for i in range(len(net_series)):
        historical = net_series[:i + 1]
        pct = float(np.sum(historical <= net_series[i]) / len(historical) * 100)
        percentiles.append(round(pct, 1))

    # Z-score of net position
    if len(net_series) > 1 and np.std(net_series) > 0:
        z_scores = ((net_series - np.mean(net_series)) / np.std(net_series)).tolist()
        z_scores = [round(z, 3) for z in z_scores]
    else:
        z_scores = [0.0] * len(net_series)

    # Build time series
    time_series = []
    step = max(1, len(data) // 500)
    for i in range(0, len(data), step):
        row = {
            "date": data[i]["date"],
            "long": data[i].get("long"),
            "short": data[i].get("short"),
            "net": data[i].get("net"),
            "net_chg": round(float(net_chg[i]), 0),
            "long_chg": round(float(long_chg[i]), 0),
            "short_chg": round(float(short_chg[i]), 0),
            "percentile": percentiles[i],
            "z_score": z_scores[i],
        }
        if data[i].get("spreading") is not None:
            row["spreading"] = data[i]["spreading"]
        # Add rolling averages
        for wname in rolling_stats:
            avg_val = rolling_stats[wname]["avg"][i]
            row[f"net_avg_{wname}"] = avg_val
        time_series.append(row)

    # Stats
    stats = {
        "current_net": float(net_series[-1]),
        "max_net": float(np.max(net_series)),
        "min_net": float(np.min(net_series)),
        "mean_net": round(float(np.mean(net_series)), 0),
        "std_net": round(float(np.std(net_series)), 0),
        "current_percentile": percentiles[-1],
        "current_z_score": z_scores[-1],
        "max_long": float(np.max(long_series)),
        "max_short": float(np.max(short_series)),
        "current_long": float(long_series[-1]),
        "current_short": float(short_series[-1]),
        "data_points": len(data),
        "date_range": {"start": data[0]["date"], "end": data[-1]["date"]},
    }

    return {
        "category": category,
        "stats": stats,
        "time_series": time_series,
        "has_spreading": cat_info["has_spreading"],
    }


@app.get("/api/cot/net-positioning")
async def cot_net_positioning():
    """Get net positioning for all categories overlaid."""
    if not cot_data.get("categories"):
        raise HTTPException(status_code=404, detail="No COT data uploaded")

    categories = cot_data["categories"]

    # Collect all dates
    all_dates = set()
    for cat_info in categories.values():
        for r in cat_info["data"]:
            all_dates.add(r["date"])
    all_dates = sorted(all_dates)

    # Build lookup per category
    cat_lookups = {}
    for cat_name, cat_info in categories.items():
        lookup = {}
        for r in cat_info["data"]:
            lookup[r["date"]] = r
        cat_lookups[cat_name] = lookup

    # Build overlaid series
    step = max(1, len(all_dates) // 500)
    series = []
    for i in range(0, len(all_dates), step):
        d = all_dates[i]
        row = {"date": d}
        for cat_name, lookup in cat_lookups.items():
            if d in lookup:
                row[cat_name] = lookup[d].get("net")
        series.append(row)

    return {
        "categories": list(categories.keys()),
        "series": series,
    }


@app.get("/api/cot/changes")
async def cot_weekly_changes():
    """Get week-over-week changes for all categories."""
    if not cot_data.get("categories"):
        raise HTTPException(status_code=404, detail="No COT data uploaded")

    categories = cot_data["categories"]
    result = {}

    for cat_name, cat_info in categories.items():
        data = cat_info["data"]
        if len(data) < 2:
            continue
        changes = []
        for i in range(max(0, len(data) - 52), len(data)):
            if i == 0:
                continue
            prev = data[i - 1]
            curr = data[i]
            net_curr = (curr.get("net") or 0)
            net_prev = (prev.get("net") or 0)
            changes.append({
                "date": curr["date"],
                "net_chg": round(net_curr - net_prev, 0),
                "long_chg": round((curr.get("long") or 0) - (prev.get("long") or 0), 0),
                "short_chg": round((curr.get("short") or 0) - (prev.get("short") or 0), 0),
            })
        result[cat_name] = changes

    return {"changes": result}


@app.get("/api/cot/extremes")
async def cot_extremes():
    """Identify extreme positioning (bullish/bearish)."""
    if not cot_data.get("categories"):
        raise HTTPException(status_code=404, detail="No COT data uploaded")

    categories = cot_data["categories"]
    extremes = []

    for cat_name, cat_info in categories.items():
        data = cat_info["data"]
        if not data:
            continue
        net_series = np.array([r.get("net", 0) or 0 for r in data], dtype=float)
        current = net_series[-1]

        # 1-year, 3-year, all-time percentiles
        n = len(net_series)
        pct_1y = float(np.sum(net_series[-52:] <= current) / min(52, n) * 100) if n > 0 else 50
        pct_3y = float(np.sum(net_series[-156:] <= current) / min(156, n) * 100) if n > 0 else 50
        pct_all = float(np.sum(net_series <= current) / n * 100) if n > 0 else 50

        # Z-score
        z = float((current - np.mean(net_series)) / np.std(net_series)) if np.std(net_series) > 0 else 0

        # Determine signal
        if pct_all > 90:
            signal = "EXTREME BULLISH"
        elif pct_all > 75:
            signal = "BULLISH"
        elif pct_all < 10:
            signal = "EXTREME BEARISH"
        elif pct_all < 25:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        # Trend (4-week direction)
        if n >= 4:
            trend = "INCREASING" if net_series[-1] > net_series[-4] else "DECREASING"
        else:
            trend = "N/A"

        extremes.append({
            "category": cat_name,
            "current_net": round(float(current), 0),
            "percentile_1y": round(pct_1y, 1),
            "percentile_3y": round(pct_3y, 1),
            "percentile_all": round(pct_all, 1),
            "z_score": round(z, 2),
            "signal": signal,
            "trend": trend,
        })

    return {"extremes": extremes}


@app.get("/api/cot/seasonal")
async def cot_seasonal():
    """Get seasonal patterns in COT data."""
    if not cot_data.get("categories"):
        raise HTTPException(status_code=404, detail="No COT data uploaded")

    categories = cot_data["categories"]
    result = {}

    for cat_name, cat_info in categories.items():
        data = cat_info["data"]
        if not data:
            continue

        # Group by year and week
        yearly_data = {}
        for r in data:
            try:
                dt = pd.to_datetime(r["date"])
                year = dt.year
                week = dt.isocalendar().week
                if year not in yearly_data:
                    yearly_data[year] = {}
                yearly_data[year][week] = r.get("net", 0) or 0
            except Exception:
                continue

        # Build seasonal series
        years = sorted(yearly_data.keys())
        seasonal_series = []
        for week in range(1, 54):
            row = {"week": week}
            vals = []
            for y in years:
                if week in yearly_data.get(y, {}):
                    row[str(y)] = yearly_data[y][week]
                    vals.append(yearly_data[y][week])
            if vals:
                row["avg"] = round(float(np.mean(vals)), 0)
                row["min"] = round(float(np.min(vals)), 0)
                row["max"] = round(float(np.max(vals)), 0)
            seasonal_series.append(row)

        result[cat_name] = {
            "years": [str(y) for y in years],
            "series": seasonal_series,
        }

    return {"seasonal": result}


# ═══════════════════════════════════════════════════════════════════════════════
# ═══  COT DECOMPOSITION (State-Space Model) & AI INSIGHT
# ═══════════════════════════════════════════════════════════════════════════════


def _get_co1_daily_prices() -> pd.DataFrame | None:
    """Get CO1 daily price data from loaded instruments."""
    for inst_id, inst in instruments.items():
        if "CO1" in inst.get("name", ""):
            daily = inst.get("timeframes", {}).get("Daily", {})
            rows = daily.get("data", [])
            if rows:
                df = pd.DataFrame(rows)
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date").reset_index(drop=True)
                return df
    return None


def _build_momentum_features(prices: pd.DataFrame, lookbacks: list[int] | None = None) -> pd.DataFrame:
    """
    Build normalized CTA-style momentum features from daily prices.
    Steps from the paper:
    1. daily PnL: dP = P_t - P_{t-1}
    2. cumulative PnL: CP_t = sum(dP_i for i <= t)
    3. For each lookback n: MOM(n) = (CP - MA(CP, n)) / sigma_price
    4. Second normalization: x(n) = MOM(n) / sigma_1y(MOM(n))
    """
    if lookbacks is None:
        lookbacks = [5, 10, 15, 20, 30, 50, 75, 100, 150, 200, 250]

    p = prices["price"].values.astype(float)
    dp = np.diff(p, prepend=p[0])  # daily PnL
    cp = np.cumsum(dp)  # cumulative PnL

    # Rolling 1-year (252 day) price volatility
    price_series = pd.Series(p)
    returns = price_series.pct_change().fillna(0)
    sigma_price = returns.rolling(252, min_periods=20).std().fillna(returns.expanding(min_periods=5).std()) * price_series
    sigma_price = sigma_price.replace(0, np.nan).ffill().fillna(1.0)

    cp_series = pd.Series(cp)
    features = pd.DataFrame({"date": prices["date"].values})

    for n in lookbacks:
        ma_cp = cp_series.rolling(n, min_periods=max(1, n // 2)).mean()
        mom = (cp_series - ma_cp) / sigma_price
        mom = mom.replace([np.inf, -np.inf], np.nan).fillna(0)
        # Second normalization by 1-year rolling std of MOM
        sigma_mom = mom.rolling(252, min_periods=20).std().fillna(mom.expanding(min_periods=5).std())
        sigma_mom = sigma_mom.replace(0, np.nan).fillna(1.0)
        x_n = mom / sigma_mom
        x_n = x_n.replace([np.inf, -np.inf], np.nan).fillna(0)
        features[f"x_{n}"] = x_n.values

    return features


def _nonlinear_reaction(u: float) -> float:
    """R(u) = u * exp((1 - u^2) / 2) — nonlinear reaction function from paper."""
    return u * np.exp((1.0 - u * u) / 2.0)


_nonlinear_reaction_vec = np.vectorize(_nonlinear_reaction)


def _run_cot_decomposition() -> dict:
    """
    Run the full COT decomposition model:
    1. Align CO1 daily prices with weekly COT Managed Money data
    2. Build momentum features from prices
    3. Decompose MM = slow_base + CTA_component + discretionary_residual
    4. Predict weekly position changes
    """
    from scipy.optimize import minimize as scipy_minimize

    # Get COT Managed Money data
    if not cot_data.get("categories"):
        raise HTTPException(status_code=400, detail="No COT data loaded")

    mm_cat = cot_data["categories"].get("Managed Money")
    if not mm_cat:
        raise HTTPException(status_code=400, detail="No Managed Money category in COT data")

    mm_rows = mm_cat["data"]
    mm_df = pd.DataFrame(mm_rows)
    mm_df["date"] = pd.to_datetime(mm_df["date"])
    mm_df = mm_df.sort_values("date").reset_index(drop=True)
    mm_df["net"] = mm_df["net"].astype(float)

    # Get CO1 prices
    price_df = _get_co1_daily_prices()

    # --- Step 1: Build slow/fast decomposition of MM ---
    # Slow = 52-week (1-year) rolling average
    mm_df["slow_base"] = mm_df["net"].rolling(52, min_periods=10).mean()
    mm_df["slow_base"] = mm_df["slow_base"].fillna(mm_df["net"].expanding(min_periods=1).mean())

    # Fast = MM - slow_base, normalized by 1-year rolling std
    mm_df["fast_raw"] = mm_df["net"] - mm_df["slow_base"]
    roll_std = mm_df["net"].rolling(52, min_periods=10).std().fillna(mm_df["net"].expanding(min_periods=5).std())
    roll_std = roll_std.replace(0, np.nan).ffill().fillna(1.0)
    mm_df["fast_normalized"] = mm_df["fast_raw"] / roll_std

    # --- Step 2 & 3: If we have price data, build CTA model ---
    cta_component = None
    discretionary = None
    model_stats = {}
    momentum_signals_ts = []
    predicted_changes = []

    if price_df is not None and len(price_df) > 20:
        lookbacks = [5, 10, 15, 20, 30, 50, 75, 100, 150, 200, 250]
        mom_features = _build_momentum_features(price_df, lookbacks)

        # Resample momentum features to weekly (Tuesday dates matching COT)
        mom_features["date"] = pd.to_datetime(mom_features["date"])
        mom_features = mom_features.set_index("date")

        # Align with COT dates
        merged = mm_df[["date", "net", "slow_base", "fast_raw", "fast_normalized"]].copy()
        merged = merged.set_index("date")

        # For each COT date, find nearest momentum features
        feature_cols = [c for c in mom_features.columns if c.startswith("x_")]
        aligned_features = []

        for cot_date in mm_df["date"]:
            # Find nearest trading day <= COT date
            mask = mom_features.index <= cot_date
            if mask.any():
                nearest = mom_features.loc[mask].iloc[-1]
                row = {"date": cot_date}
                for fc in feature_cols:
                    row[fc] = float(nearest[fc]) if not np.isnan(nearest[fc]) else 0.0
                aligned_features.append(row)
            else:
                row = {"date": cot_date}
                for fc in feature_cols:
                    row[fc] = 0.0
                aligned_features.append(row)

        feat_df = pd.DataFrame(aligned_features)
        feat_df["date"] = pd.to_datetime(feat_df["date"])

        # Merge with MM data
        model_df = mm_df.merge(feat_df, on="date", how="inner")

        # Only use rows where we have valid features
        has_features = model_df[feature_cols].abs().sum(axis=1) > 0
        model_df_valid = model_df[has_features].copy().reset_index(drop=True)

        if len(model_df_valid) >= 20:
            # Apply nonlinear reaction to create K=3 CTA signals
            K = 3
            n_lookbacks = len(lookbacks)

            # Use L1-regularized regression for the 2-layer model
            # Layer 1: w(k, n) weights shared across signals
            # Layer 2: W_m(k) market-specific weights
            # Simplified: direct Lasso on nonlinear-transformed features

            y = model_df_valid["fast_normalized"].values
            X_raw = model_df_valid[feature_cols].values

            # Apply nonlinear reaction to raw features
            X_nonlin = _nonlinear_reaction_vec(X_raw)

            # Use rolling 2-year training window for out-of-sample
            train_window = min(104, len(y) // 2)  # 2 years or half data
            n_total = len(y)

            cta_pred = np.full(n_total, np.nan)
            bias_pred = np.full(n_total, np.nan)
            weights_history = []

            for t in range(train_window, n_total):
                t_start = max(0, t - train_window)
                y_train = y[t_start:t]
                X_train = X_nonlin[t_start:t]

                # L1 regularized (Lasso-like) regression
                # Simple: use pseudo-inverse with L1 penalty via thresholding
                try:
                    # Ridge + L1 thresholding
                    lam1 = 0.1  # L1 penalty
                    XtX = X_train.T @ X_train + 0.01 * np.eye(X_train.shape[1])
                    Xty = X_train.T @ y_train
                    w = np.linalg.solve(XtX, Xty)
                    # Soft threshold for sparsity
                    w = np.sign(w) * np.maximum(np.abs(w) - lam1, 0)
                    cta_pred[t] = X_nonlin[t] @ w
                    bias_pred[t] = y[t] - cta_pred[t]
                    weights_history.append(w.copy())
                except Exception:
                    cta_pred[t] = 0.0
                    bias_pred[t] = y[t]

            # Convert back to contract space
            roll_std_arr = roll_std.values
            if len(roll_std_arr) < len(model_df_valid):
                roll_std_matched = np.ones(len(model_df_valid))
                for i, idx in enumerate(model_df_valid.index):
                    if idx < len(roll_std_arr):
                        roll_std_matched[i] = roll_std_arr[idx]
            else:
                roll_std_matched = roll_std_arr[model_df_valid.index]

            cta_contracts = cta_pred * roll_std_matched
            disc_contracts = bias_pred * roll_std_matched

            # Build time series output
            valid_mask = ~np.isnan(cta_pred)

            for i in range(len(model_df_valid)):
                row = {
                    "date": model_df_valid.iloc[i]["date"].strftime("%Y-%m-%d"),
                    "mm_net": float(model_df_valid.iloc[i]["net"]),
                    "slow_base": float(model_df_valid.iloc[i]["slow_base"]),
                    "fast_component": float(model_df_valid.iloc[i]["fast_raw"]),
                    "cta_component": float(cta_contracts[i]) if valid_mask[i] else None,
                    "discretionary": float(disc_contracts[i]) if valid_mask[i] else None,
                    "fast_normalized": float(model_df_valid.iloc[i]["fast_normalized"]),
                    "cta_normalized": float(cta_pred[i]) if valid_mask[i] else None,
                }
                momentum_signals_ts.append(row)

            # Model stats
            valid_idx = valid_mask & ~np.isnan(y)
            if valid_idx.sum() > 5:
                r2_oos = 1.0 - np.nansum((y[valid_idx] - cta_pred[valid_idx]) ** 2) / np.nansum((y[valid_idx] - np.nanmean(y[valid_idx])) ** 2)
                corr_oos = float(np.corrcoef(y[valid_idx], cta_pred[valid_idx])[0, 1])

                model_stats = {
                    "r2_out_of_sample": round(float(r2_oos), 4),
                    "correlation_oos": round(corr_oos, 4),
                    "pct_explained": round(float(r2_oos) * 100, 1),
                    "training_window_weeks": train_window,
                    "total_observations": int(valid_idx.sum()),
                    "num_features": len(feature_cols),
                    "lookbacks_used": lookbacks,
                }

            # Predicted weekly change (dMM = sigma * (y_hat_t - y_hat_{t-5}))
            for i in range(5, len(model_df_valid)):
                if valid_mask[i] and valid_mask[i - 5]:
                    predicted_chg = roll_std_matched[i] * (cta_pred[i] - cta_pred[i - 5])
                    actual_chg = float(model_df_valid.iloc[i]["net"]) - float(model_df_valid.iloc[i - 5]["net"])
                    predicted_changes.append({
                        "date": model_df_valid.iloc[i]["date"].strftime("%Y-%m-%d"),
                        "predicted_change": round(float(predicted_chg), 0),
                        "actual_change": round(actual_chg, 0),
                    })

            # Current signal weights (latest)
            if weights_history:
                latest_w = weights_history[-1]
                signal_weights = []
                for j, lb in enumerate(lookbacks):
                    if j < len(latest_w):
                        signal_weights.append({"lookback": lb, "weight": round(float(latest_w[j]), 4)})
                model_stats["signal_weights"] = signal_weights

    else:
        # No price data — just do slow/fast decomposition
        for i in range(len(mm_df)):
            momentum_signals_ts.append({
                "date": mm_df.iloc[i]["date"].strftime("%Y-%m-%d"),
                "mm_net": float(mm_df.iloc[i]["net"]),
                "slow_base": float(mm_df.iloc[i]["slow_base"]),
                "fast_component": float(mm_df.iloc[i]["fast_raw"]),
                "cta_component": None,
                "discretionary": None,
                "fast_normalized": float(mm_df.iloc[i]["fast_normalized"]),
                "cta_normalized": None,
            })
        model_stats = {"message": "No CO1 price data available — showing slow/fast decomposition only"}

    # Clean NaN/Inf values
    def _clean(v):
        if v is None:
            return None
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            return None
        return v

    for row in momentum_signals_ts:
        for k in row:
            if k != "date":
                row[k] = _clean(row[k])

    for row in predicted_changes:
        for k in row:
            if k != "date":
                row[k] = _clean(row[k])

    return {
        "decomposition": momentum_signals_ts,
        "predicted_changes": predicted_changes,
        "model_stats": model_stats,
        "has_price_model": price_df is not None and len(momentum_signals_ts) > 0 and any(r.get("cta_component") is not None for r in momentum_signals_ts),
    }


@app.get("/api/cot/decomposition")
async def cot_decomposition():
    """COT state-space decomposition: slow base + CTA trend-following + discretionary."""
    if not cot_data.get("categories"):
        raise HTTPException(status_code=400, detail="No COT data loaded")
    try:
        result = _run_cot_decomposition()
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cot/ai-insight")
async def cot_ai_insight():
    """AI-driven analysis of COT + price data with positioning forecast."""
    if not cot_data.get("categories"):
        raise HTTPException(status_code=400, detail="No COT data loaded")

    cats = cot_data["categories"]
    mm_cat = cats.get("Managed Money", {})
    mm_rows = mm_cat.get("data", [])
    if not mm_rows:
        raise HTTPException(status_code=400, detail="No Managed Money data")

    mm_df = pd.DataFrame(mm_rows)
    mm_df["date"] = pd.to_datetime(mm_df["date"])
    mm_df = mm_df.sort_values("date").reset_index(drop=True)
    mm_df["net"] = mm_df["net"].astype(float)

    # Get price data if available
    price_df = _get_co1_daily_prices()
    price_context = ""
    price_trend = "N/A"
    price_last = None

    if price_df is not None and len(price_df) > 5:
        p = price_df["price"].values
        price_last = float(p[-1])
        # Recent price trend
        if len(p) >= 20:
            sma20 = float(np.mean(p[-20:]))
            sma50 = float(np.mean(p[-min(50, len(p)):]))
            if p[-1] > sma20 > sma50:
                price_trend = "UPTREND"
            elif p[-1] < sma20 < sma50:
                price_trend = "DOWNTREND"
            elif p[-1] > sma20:
                price_trend = "RECOVERING"
            else:
                price_trend = "WEAKENING"

            ret_1w = (p[-1] / p[-5] - 1) * 100 if len(p) >= 5 else 0
            ret_1m = (p[-1] / p[-20] - 1) * 100 if len(p) >= 20 else 0
            vol_20d = float(np.std(np.diff(np.log(p[-21:]))) * np.sqrt(252) * 100) if len(p) >= 21 else 0

            price_context = f"CO1 at ${price_last:.2f}, {price_trend}. 1W return: {ret_1w:+.1f}%, 1M return: {ret_1m:+.1f}%. 20D annualized vol: {vol_20d:.1f}%."

    # --- Analyze all categories ---
    category_analysis = {}
    for cat_name, cat_info in cats.items():
        data = cat_info.get("data", [])
        if len(data) < 4:
            continue
        df = pd.DataFrame(data)
        df["net"] = df["net"].astype(float)
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else latest
        net_now = float(latest["net"])
        net_prev = float(prev["net"])
        chg = net_now - net_prev

        # 4-week trend
        if len(df) >= 4:
            net_4w_ago = float(df.iloc[-4]["net"])
            trend_4w = net_now - net_4w_ago
        else:
            trend_4w = 0

        # 12-week trend
        if len(df) >= 12:
            net_12w_ago = float(df.iloc[-12]["net"])
            trend_12w = net_now - net_12w_ago
        else:
            trend_12w = 0

        # Historical percentile
        all_nets = df["net"].astype(float).values
        pctl = float(np.sum(all_nets <= net_now) / len(all_nets) * 100)

        # Z-score
        mean_52 = float(np.mean(all_nets[-52:])) if len(all_nets) >= 52 else float(np.mean(all_nets))
        std_52 = float(np.std(all_nets[-52:])) if len(all_nets) >= 52 else float(np.std(all_nets))
        z = (net_now - mean_52) / std_52 if std_52 > 0 else 0

        # Consecutive weeks direction
        consec = 0
        direction = "flat"
        for i in range(len(df) - 1, 0, -1):
            c = float(df.iloc[i]["net"]) - float(df.iloc[i - 1]["net"])
            if i == len(df) - 1:
                direction = "increasing" if c > 0 else "decreasing" if c < 0 else "flat"
            if (direction == "increasing" and c > 0) or (direction == "decreasing" and c < 0):
                consec += 1
            else:
                break

        category_analysis[cat_name] = {
            "net": net_now,
            "weekly_change": chg,
            "trend_4w": trend_4w,
            "trend_12w": trend_12w,
            "percentile": pctl,
            "z_score": z,
            "direction": direction,
            "consecutive_weeks": consec,
        }

    # --- Run decomposition for CTA insight ---
    decomp_insight = ""
    forecast_direction = "NEUTRAL"
    forecast_confidence = 50
    predicted_weekly_chg = 0.0

    try:
        decomp = _run_cot_decomposition()
        if decomp.get("has_price_model"):
            ts = decomp["decomposition"]
            valid_ts = [r for r in ts if r.get("cta_component") is not None]
            if valid_ts:
                latest = valid_ts[-1]
                cta_now = latest["cta_component"]
                disc_now = latest["discretionary"]
                mm_net = latest["mm_net"]
                slow = latest["slow_base"]

                cta_pct = abs(cta_now) / (abs(cta_now) + abs(disc_now) + 1) * 100
                disc_pct = 100 - cta_pct

                # Trend of CTA component
                if len(valid_ts) >= 4:
                    cta_4w_ago = valid_ts[-4]["cta_component"]
                    cta_trend = "ADDING LONGS" if cta_now > cta_4w_ago else "REDUCING LONGS" if cta_now < cta_4w_ago else "FLAT"
                else:
                    cta_trend = "N/A"

                decomp_insight = (
                    f"CTA/trend-following explains ~{cta_pct:.0f}% of fast positioning "
                    f"(current CTA: {cta_now:+,.0f} contracts, discretionary: {disc_now:+,.0f}). "
                    f"CTA is {cta_trend} over past 4 weeks. "
                )

                # Predicted changes
                pred_chgs = decomp.get("predicted_changes", [])
                if pred_chgs:
                    last_pred = pred_chgs[-1]
                    predicted_weekly_chg = last_pred.get("predicted_change", 0) or 0

                    # Recent accuracy
                    recent = pred_chgs[-12:] if len(pred_chgs) >= 12 else pred_chgs
                    correct_dir = sum(1 for p in recent if
                                      (p.get("predicted_change", 0) or 0) * (p.get("actual_change", 0) or 0) > 0)
                    accuracy = correct_dir / len(recent) * 100 if recent else 0

                    decomp_insight += f"Model predicts {predicted_weekly_chg:+,.0f} contract change next week (directional accuracy last 12w: {accuracy:.0f}%). "

                    r2 = decomp.get("model_stats", {}).get("r2_out_of_sample", 0)
                    decomp_insight += f"Out-of-sample R²: {r2:.2f}. "
    except Exception:
        decomp_insight = ""

    # --- Build the AI insight paragraph ---
    mm_info = category_analysis.get("Managed Money", {})
    prod_info = category_analysis.get("Producers", {})
    swap_info = category_analysis.get("Swap Dealers", {})

    # Determine overall forecast
    mm_z = mm_info.get("z_score", 0)
    mm_pctl = mm_info.get("percentile", 50)
    mm_dir = mm_info.get("direction", "flat")
    mm_consec = mm_info.get("consecutive_weeks", 0)

    if mm_dir == "increasing" and mm_z > 0.5:
        forecast_direction = "LIKELY ADD LONGS"
        forecast_confidence = min(85, 55 + mm_consec * 5 + max(0, mm_z * 10))
    elif mm_dir == "increasing" and mm_z <= 0.5:
        forecast_direction = "MODESTLY ADD LONGS"
        forecast_confidence = min(70, 50 + mm_consec * 3)
    elif mm_dir == "decreasing" and mm_z < -0.5:
        forecast_direction = "LIKELY REDUCE/ADD SHORTS"
        forecast_confidence = min(85, 55 + mm_consec * 5 + max(0, abs(mm_z) * 10))
    elif mm_dir == "decreasing" and mm_z >= -0.5:
        forecast_direction = "MODESTLY REDUCE LONGS"
        forecast_confidence = min(70, 50 + mm_consec * 3)
    else:
        forecast_direction = "NEUTRAL / RANGE-BOUND"
        forecast_confidence = 45

    # Adjust with price trend
    if price_trend in ["UPTREND", "RECOVERING"] and "ADD LONGS" in forecast_direction:
        forecast_confidence = min(90, forecast_confidence + 10)
    elif price_trend in ["DOWNTREND", "WEAKENING"] and "SHORTS" in forecast_direction:
        forecast_confidence = min(90, forecast_confidence + 10)

    # Build paragraph
    paragraph = f"**Managed Money** currently holds {mm_info.get('net', 0):+,.0f} net contracts "
    paragraph += f"(percentile: {mm_pctl:.0f}%, z-score: {mm_z:+.2f}). "
    paragraph += f"Positioning has been {mm_dir} for {mm_consec} consecutive week{'s' if mm_consec != 1 else ''}, "
    paragraph += f"with a 4-week change of {mm_info.get('trend_4w', 0):+,.0f} and 12-week change of {mm_info.get('trend_12w', 0):+,.0f} contracts. "

    if prod_info:
        paragraph += f"\n\n**Producers** are at {prod_info.get('net', 0):+,.0f} net (hedging), {prod_info.get('direction', 'flat')} over {prod_info.get('consecutive_weeks', 0)} weeks. "
    if swap_info:
        paragraph += f"**Swap Dealers** at {swap_info.get('net', 0):+,.0f} net, {swap_info.get('direction', 'flat')}. "

    if price_context:
        paragraph += f"\n\n**Price Context:** {price_context} "

    if decomp_insight:
        paragraph += f"\n\n**CTA Decomposition:** {decomp_insight}"

    paragraph += f"\n\n**Forecast:** Based on momentum, positioning trends, and {'the CTA model, ' if decomp_insight else ''}"
    paragraph += f"Managed Money is **{forecast_direction}** in the coming weeks "
    paragraph += f"(confidence: {forecast_confidence:.0f}%). "

    if predicted_weekly_chg != 0:
        paragraph += f"The CTA-based model estimates a change of approximately **{predicted_weekly_chg:+,.0f}** contracts next week. "

    # Extreme positioning warning
    if mm_pctl > 90:
        paragraph += f"\n\n**Warning:** Managed Money positioning is in the {mm_pctl:.0f}th percentile — historically extreme BULLISH territory. Risk of mean reversion/liquidation is elevated."
    elif mm_pctl < 10:
        paragraph += f"\n\n**Warning:** Managed Money positioning is in the {mm_pctl:.0f}th percentile — historically extreme BEARISH territory. Risk of short-covering rally is elevated."

    # Clean any NaN/Inf in category_analysis
    def _clean_dict(d):
        cleaned = {}
        for k, v in d.items():
            if isinstance(v, dict):
                cleaned[k] = _clean_dict(v)
            elif isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                cleaned[k] = None
            else:
                cleaned[k] = v
        return cleaned

    return {
        "paragraph": paragraph,
        "forecast": {
            "direction": forecast_direction,
            "confidence": round(forecast_confidence, 1),
            "predicted_weekly_change": round(predicted_weekly_chg, 0) if predicted_weekly_chg else None,
        },
        "category_analysis": _clean_dict(category_analysis),
        "price_trend": price_trend,
        "price_last": price_last,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ═══  MULTI-COMMODITY COT DATA (Brent, WTI, Gasoil)
# ═══════════════════════════════════════════════════════════════════════════════

cot_multi_data: dict = {}  # {"brent": [...], "wti": [...], "gasoil": [...]}

# ── Pricing data (prices workbook) ─────────────────────────────────────────
_PRICING_CACHE = None


def _load_pricing_raw():
    """Load the parsed pricing workbook (all price/crack/swap series)."""
    global _PRICING_CACHE
    if _PRICING_CACHE is not None:
        return _PRICING_CACHE
    path = os.path.join(os.path.dirname(__file__), "pricing_data.json")
    with open(path) as f:
        _PRICING_CACHE = _json.load(f)
    return _PRICING_CACHE


@app.get("/api/pricing/groups")
async def pricing_groups():
    """List available pricing sheets/groups with their series (metadata only)."""
    data = _load_pricing_raw()
    out = []
    for g in data.get("groups", []):
        out.append({
            "sheet": g["sheet"],
            "title": g["title"],
            "n_series": len(g["series"]),
            "series": [{"label": s["label"], "ticker": s["ticker"], "n": len(s["dates"]),
                        "last_date": s["dates"][-1] if s["dates"] else None,
                        "last_value": s["values"][-1] if s["values"] else None} for s in g["series"]],
        })
    return {"groups": out, "generated": data.get("generated")}


@app.get("/api/pricing/data")
async def pricing_data_endpoint(group: str = Query(...)):
    """Return full time series for every series within a single pricing group."""
    data = _pricing_with_live()
    for g in data.get("groups", []):
        if g["sheet"].lower() == group.lower():
            return {"sheet": g["sheet"], "title": g["title"], "series": g["series"],
                    "live": data.get("live")}
    raise HTTPException(status_code=404, detail=f"No pricing group '{group}'")


# ── Live price feed (pushed by the local Bloomberg bridge) ─────────────────
_LIVE_TICKS = None
_LIVE_META = {"generated": None, "source": None}


def _live_ticks_path():
    return os.path.join(os.path.dirname(__file__), "live_ticks.json")


def _get_live_ticks():
    """In-memory map of label -> {value, ts, prev}. Loaded from disk once."""
    global _LIVE_TICKS
    if _LIVE_TICKS is None:
        _LIVE_TICKS = {}
        try:
            with open(_live_ticks_path()) as f:
                blob = _json.load(f)
            _LIVE_TICKS = blob.get("ticks", {})
            _LIVE_META["generated"] = blob.get("generated")
            _LIVE_META["source"] = blob.get("source")
        except FileNotFoundError:
            pass
        except Exception:
            _LIVE_TICKS = {}
    return _LIVE_TICKS


def _pricing_with_live():
    """Pricing workbook with the latest live ticks overlaid on each series'
    front value (replacing today's point or appending a fresh one)."""
    base = _load_pricing_raw()
    ticks = _get_live_ticks()
    if not ticks:
        return base
    today = datetime.utcnow().strftime("%Y-%m-%d")
    out = dict(base)
    new_groups = []
    for g in base.get("groups", []):
        ng = dict(g)
        new_series = []
        for s in g.get("series", []):
            tk = ticks.get(s.get("label"))
            if tk is None:
                tk = ticks.get(s.get("ticker"))
            if tk is not None and s.get("values"):
                try:
                    v = float(tk["value"])
                except (TypeError, ValueError, KeyError):
                    new_series.append(s)
                    continue
                ns = dict(s)
                dates = list(s.get("dates", []))
                values = list(s.get("values", []))
                if dates and dates[-1] == today:
                    values[-1] = v
                else:
                    dates.append(today)
                    values.append(v)
                ns["dates"] = dates
                ns["values"] = values
                ns["live"] = True
                ns["live_ts"] = tk.get("ts")
                new_series.append(ns)
            else:
                new_series.append(s)
        ng["series"] = new_series
        new_groups.append(ng)
    out["groups"] = new_groups
    out["live"] = {
        "count": len(ticks),
        "generated": _LIVE_META.get("generated"),
        "source": _LIVE_META.get("source"),
    }
    return out


@app.post("/api/pricing/live")
async def pricing_live_ingest(request: Request):
    """Ingest live prices pushed by the local Bloomberg bridge. Auth is handled
    by the gate middleware via the X-Ingest-Token header."""
    body = await request.json()
    if body.get("clear"):
        _get_live_ticks().clear()
        _LIVE_META["generated"] = None
        _LIVE_META["source"] = None
        try:
            os.remove(_live_ticks_path())
        except FileNotFoundError:
            pass
        return {"ok": True, "cleared": True}
    raw = body.get("ticks", body)
    incoming = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            incoming[str(k)] = v
    elif isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict) and "label" in row:
                incoming[str(row["label"])] = row.get("value")
    now = datetime.utcnow().isoformat() + "Z"
    ticks = _get_live_ticks()
    n = 0
    for lab, val in incoming.items():
        if val is None:
            continue
        try:
            fv = float(val)
        except (TypeError, ValueError):
            continue
        prev = ticks.get(lab, {}).get("value")
        ticks[lab] = {"value": fv, "ts": now, "prev": prev}
        n += 1
    _LIVE_META["generated"] = now
    _LIVE_META["source"] = body.get("source", "bloomberg-bridge")
    try:
        with open(_live_ticks_path(), "w") as f:
            _json.dump({"ticks": ticks, "generated": now,
                        "source": _LIVE_META["source"]}, f)
    except Exception:
        pass
    return {"ok": True, "updated": n, "generated": now}


@app.get("/api/pricing/live")
async def pricing_live_read():
    """Return the current live ticks (for the frontend LIVE overlay/badge)."""
    ticks = _get_live_ticks()
    gen = _LIVE_META.get("generated")
    stale = None
    if gen:
        try:
            ts = datetime.fromisoformat(gen.replace("Z", ""))
            stale = round((datetime.utcnow() - ts).total_seconds(), 1)
        except ValueError:
            stale = None
    return {
        "ticks": ticks,
        "count": len(ticks),
        "generated": gen,
        "source": _LIVE_META.get("source"),
        "stale_seconds": stale,
    }


# ── Live positioning feed (order-level model grid, pushed by the bridge) ────
_POS_DATA = None
_POS_META = {"generated": None, "source": None}


def _pos_path():
    return os.path.join(os.path.dirname(__file__), "live_positioning.json")


def _get_positioning():
    """In-memory structured positioning payload. Loaded from disk once."""
    global _POS_DATA
    if _POS_DATA is None:
        _POS_DATA = {}
        try:
            with open(_pos_path()) as f:
                blob = _json.load(f)
            _POS_DATA = blob.get("data", {})
            _POS_META["generated"] = blob.get("generated")
            _POS_META["source"] = blob.get("source")
        except FileNotFoundError:
            pass
        except Exception:
            _POS_DATA = {}
    return _POS_DATA


@app.post("/api/positioning/live")
async def positioning_live_ingest(request: Request):
    """Ingest the live positioning grid (instruments -> header stats + order-level
    rows) pushed by the local bridge. Auth via X-Ingest-Token in the gate."""
    global _POS_DATA
    body = await request.json()
    if body.get("clear"):
        _POS_DATA = {}
        _POS_META["generated"] = None
        _POS_META["source"] = None
        try:
            os.remove(_pos_path())
        except FileNotFoundError:
            pass
        return {"ok": True, "cleared": True}
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return {"ok": False, "error": "expected {data: {...}}"}
    now = datetime.utcnow().isoformat() + "Z"
    _POS_DATA = data
    _POS_META["generated"] = now
    _POS_META["source"] = body.get("source", "bloomberg-bridge")
    try:
        with open(_pos_path(), "w") as f:
            _json.dump({"data": data, "generated": now,
                        "source": _POS_META["source"]}, f)
    except Exception:
        pass
    n = len(data.get("instruments", [])) if isinstance(data, dict) else 0
    return {"ok": True, "instruments": n, "generated": now}


@app.get("/api/positioning/live")
async def positioning_live_read():
    """Return the current live positioning grid (for the Money Positioning panel)."""
    data = _get_positioning()
    gen = _POS_META.get("generated")
    stale = None
    if gen:
        try:
            ts = datetime.fromisoformat(gen.replace("Z", ""))
            stale = round((datetime.utcnow() - ts).total_seconds(), 1)
        except ValueError:
            stale = None
    return {
        "data": data,
        "generated": gen,
        "source": _POS_META.get("source"),
        "stale_seconds": stale,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ═══  MARKET INTELLIGENCE  (cross-source commentary + trajectory)
# ═══════════════════════════════════════════════════════════════════════════════
def _iir_outage_summary():
    """Best-effort snapshot of currently-offline refining capacity from IIR.
    Returns None if the IIR data/endpoint isn't reachable offline."""
    try:
        import app.market_intel as _mi  # noqa
    except Exception:
        pass
    try:
        cache = globals().get("_IIR_OUTAGE_CACHE")
        if cache is not None:
            return cache
    except Exception:
        pass
    return None


def _build_market_context():
    import app.market_intel as mi
    pricing = _pricing_with_live()
    margins = _load_margins_raw()
    ctx = mi.build_context(cot_multi_data, pricing, margins)
    if pricing.get("live"):
        ctx["live"] = pricing["live"]
    outages = _iir_outage_summary()
    if outages:
        ctx["outages"] = outages
    news = mi.load_market_news()
    if news:
        ctx["news_headline"] = news[:500]
    return ctx


@app.get("/api/market/context")
async def market_context():
    """Full cross-source market snapshot (positioning, pricing, cracks, swaps, margins)."""
    return _build_market_context()


@app.get("/api/market/briefing")
async def market_briefing(product: str = Query("crude"), region: str = Query("US"),
                          use_llm: bool = Query(True)):
    """Generate a product/region market briefing from the cross-source snapshot."""
    import app.market_intel as mi
    ctx = _build_market_context()
    base = mi.generate_briefing(ctx, product, region)
    if base.get("available") and use_llm:
        base = mi.llm_polish_briefing(ctx, product, region, base)
        if not base.get("llm"):
            base["llm_note"] = mi._llm_error() or ("No LLM key configured" if not mi._llm_available() else None)
    return base


@app.get("/api/market/news")
async def market_news(product: str = Query(None)):
    """Latest uploaded analyst market news (optionally filtered to a product)."""
    import app.market_intel as mi
    txt = mi.news_excerpt(product) if product else mi.load_market_news()
    return {"available": bool(txt), "product": product, "news": txt}


@app.get("/api/market/briefings")
async def market_briefings_all(use_llm: bool = Query(False)):
    """Generate the full grid of briefings (all products × regions)."""
    import app.market_intel as mi
    ctx = _build_market_context()
    regions = ["US", "UK", "DUBAI", "SING"]
    out = []
    for p in mi.PRODUCTS:
        for rg in regions:
            b = mi.generate_briefing(ctx, p, rg)
            if b.get("available") and use_llm:
                b = mi.llm_polish_briefing(ctx, p, rg, b)
            out.append(b)
    return {"generated": ctx.get("generated"), "briefings": out, "llm_enabled": mi._llm_available()}


@app.get("/api/market/crossmarket")
async def market_crossmarket():
    """Combined intelligence view: current state + directional trajectory per
    product, fusing positioning, pricing, term structure, cracks and margins,
    plus a flows/outages → product-impact linkage."""
    import app.market_intel as mi
    ctx = _build_market_context()
    pricing = _pricing_with_live()
    curves = mi.build_curves(pricing)
    news_hits = mi._news_hits(["crude", "distillate", "gasoline"])
    desk = mi.desk_recommendations(ctx, curves, news_hits)

    def _score_product(prod):
        """Directional score in [-100,100] from crack pctile/trend, curve, positioning, margin."""
        score = 0.0
        drivers = []
        if prod == "crude":
            fl = ctx["flat"].get("Brent") or ctx["flat"].get("WTI")
            cv = ctx["curve"].get("Brent") or ctx["curve"].get("WTI")
            ct = ctx["cot"].get("brent") or ctx["cot"].get("wti")
            if cv:
                s = 25 if cv["shape"] == "backwardation" else -25 if cv["shape"] == "contango" else 0
                score += s
                drivers.append(f"Curve {cv['shape']} (M1-M2 {cv['m1_m2']:+.2f})")
            if fl:
                s = max(-20, min(20, fl["wow"] * 6))
                score += s
                drivers.append(f"Flat {fl['trend']} ({fl['wow']:+.2f} w/w)")
            if ct:
                # crowded longs are a headwind; light positioning is a tailwind
                s = -(ct["pctile"] - 50) * 0.4
                score += s
                drivers.append(f"MM {ct['pctile']:.0f}th pctile ({ct['stance']})")
        else:
            crack_lab = {"distillate": "GO-Brent 1", "gasoline": "RBOB-Brent 1"}.get(prod)
            crack = ctx["cracks"].get(crack_lab)
            if prod == "distillate":
                crack = crack or ctx["cracks"].get("HO-WTI 1")
            if prod == "gasoline":
                crack = crack or ctx["cracks"].get("RBOB-WTI 1")
            if crack:
                s = max(-25, min(25, crack["wow"] * 8))
                score += s
                drivers.append(f"{crack['label']} {crack['wow']:+.2f} w/w")
                s2 = (crack["pctile"] - 50) * 0.3
                score += s2
                drivers.append(f"Crack {crack['pctile']:.0f}th pctile")
            reg_margin = "US Gulf Coast" if prod == "gasoline" else "North-West Europe"
            mgs = [m for m in ctx.get("margins", []) if m["region"] == reg_margin]
            if mgs:
                mg = max(mgs, key=lambda m: m["seasonal_pctile"] or 0)
                s = ((mg["seasonal_pctile"] or 50) - 50) * 0.4
                score += s
                drivers.append(f"{mg['name']} {mg['seasonal_pctile']:.0f}th seasonal pctile")
        score = max(-100, min(100, score))
        bias = "BULLISH" if score > 20 else "BEARISH" if score < -20 else "NEUTRAL"
        return {"product": prod, "score": round(score, 1), "bias": bias, "drivers": drivers}

    trajectory = [_score_product(p) for p in ["crude", "distillate", "gasoline"]]

    # Flow/outage → product linkage (qualitative, data-aware)
    linkage = [
        {"signal": "Refinery outage / run cut (IIR, Genscape)",
         "impact": "Reduces product supply → widens the affected crack (bullish gasoline/distillate) "
                   "and cuts crude runs (bearish prompt crude/differentials for the feed grade)."},
        {"signal": "Crude import surge into a region (Kpler)",
         "impact": "Signals higher forward runs → more product supply → bearish local cracks with a lag; "
                   "bullish crude differentials near-term."},
        {"signal": "JODI stock draw in a region",
         "impact": "Confirms tightening balance → supportive for that product's crack and time spreads."},
        {"signal": "Term-structure flip (curve)",
         "impact": "Backwardation ↑ = prompt tightness (bullish); contango ↑ = prompt length (bearish)."},
    ]

    return {
        "generated": ctx.get("generated"),
        "flat": ctx["flat"], "curve": ctx["curve"], "cot": ctx["cot"],
        "cracks": ctx["cracks"], "swaps": ctx["swaps"], "margins": ctx["margins"],
        "trajectory": trajectory,
        "curves": curves,
        "desk": desk,
        "linkage": linkage,
        "outages": ctx.get("outages"),
        "live": ctx.get("live"),
    }


_COT_MULTI_LABELS = {
    "brent": "ICE Brent Crude",
    "wti": "NYMEX WTI Crude",
    "gasoil": "ICE Gasoil",
    "rbob": "NYMEX RBOB Gasoline",
}


@app.on_event("startup")
async def load_cot_multi_data():
    """Load multi-commodity COT data (Brent, WTI, Gasoil) — always, even in LEAN_MODE."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    if not os.path.isdir(data_dir):
        data_dir = "/app/data"
    # Prefer the combined COT workbook (WTI/Brent/Gasoil/RBOB in one file)
    combined = os.path.join(os.path.dirname(__file__), "cot_latest.xlsx")
    if os.path.isfile(combined):
        try:
            _load_cot_latest_all(combined)
            return
        except Exception as exc:
            print(f"[STARTUP] Failed combined COT load: {exc}")
    _cot_multi_files = {
        "brent": os.path.join(data_dir, "brentCOT.xlsx"),
        "wti": os.path.join(data_dir, "wticot.xlsx"),
        "gasoil": os.path.join(data_dir, "gasoilcot.xlsx"),
    }
    for ckey, cpath in _cot_multi_files.items():
        if os.path.isfile(cpath):
            try:
                _load_cot_multi(ckey, cpath)
                print(f"[STARTUP] Loaded COT multi: {ckey} ({len(cot_multi_data[ckey])} rows)")
            except Exception as exc:
                print(f"[STARTUP] Failed COT multi {ckey}: {exc}")


def _load_cot_multi(key: str, path: str):
    """Parse multi-header COT Excel (Brent/WTI/Gasoil format)."""
    df = pd.read_excel(path, header=None)
    # Row 0=Category, 1=Group, 2=Type, data starts row 4
    cols = []
    for c in range(df.shape[1]):
        grp = str(df.iloc[1, c]).strip() if pd.notna(df.iloc[1, c]) else "-"
        typ = str(df.iloc[2, c]).strip() if pd.notna(df.iloc[2, c]) else "-"
        if c == 0:
            cols.append("date")
        elif c == df.shape[1] - 1:
            cols.append("price")
        else:
            cols.append(f"{grp}|{typ}")
    data = df.iloc[4:].copy()
    data.columns = cols
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date"])
    data = data.sort_values("date").reset_index(drop=True)
    for c in cols[1:]:
        data[c] = pd.to_numeric(data[c], errors="coerce")
    cot_multi_data[key] = data


# --- Combined COT workbook loader (WTI/Brent/Gasoil/RBOB in one file) ---
_COT_LATEST_SHEETS = {"wti": "WTI", "brent": "Brent", "gasoil": "Gasoil", "rbob": "RBOB"}
# Front-month price ticker in pricing_data.json used to attach a price column
_COT_PRICE_TICKER = {"wti": "CL1", "brent": "CO1", "gasoil": "QS1", "rbob": "XB1"}


def _cot_latest_colname(grp, typ):
    """Normalize a (group, type) header pair from the combined COT workbook
    into the canonical 'Group|Type' name the endpoints expect."""
    grp = (str(grp).strip() if grp is not None else "-")
    typ = (str(typ).strip() if typ is not None else "-")
    if grp == "Total Commercial Trade":
        grp = "Total Commercial Traders"
    if typ == "Total Open" or typ.startswith("Total Open"):
        typ = "Total Open Interest"
    elif typ.startswith("Net as %"):
        typ = "Net as % of Open Interest"
    return f"{grp}|{typ}"


def _price_series_from_pricing(ticker):
    """Return a date->price dict for a front-month ticker from pricing_data.json."""
    try:
        pdata = _load_pricing_raw()
    except Exception:
        return None
    for g in pdata.get("groups", []):
        for s in g.get("series", []):
            if s.get("ticker") == ticker or s.get("label") == ticker:
                return dict(zip(s["dates"], s["values"]))
    return None


def _load_cot_latest_all(path):
    """Parse the combined COT workbook (sheets WTI/Brent/Gasoil/RBOB) into
    cot_multi_data, attaching a front-month price column from pricing data."""
    for key, sheet in _COT_LATEST_SHEETS.items():
        try:
            raw = pd.read_excel(path, sheet_name=sheet, header=None)
        except Exception as exc:
            print(f"[STARTUP] COT latest: no sheet {sheet}: {exc}")
            continue
        cols = ["date"]
        for c in range(1, raw.shape[1]):
            cols.append(_cot_latest_colname(raw.iloc[1, c], raw.iloc[2, c]))
        data = raw.iloc[4:].copy()
        data.columns = cols[: raw.shape[1]]
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        data = data.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        for c in data.columns:
            if c != "date":
                data[c] = pd.to_numeric(data[c], errors="coerce")
        # Attach price from pricing data (as-of nearest prior trading day)
        pmap = _price_series_from_pricing(_COT_PRICE_TICKER.get(key, ""))
        if pmap:
            pser = pd.Series(pmap)
            pser.index = pd.to_datetime(pser.index)
            pser = pser.sort_index()
            pdf = pd.DataFrame({"date": pser.index, "price": pser.values})
            data = pd.merge_asof(data, pdf, on="date", direction="backward")
        else:
            data["price"] = np.nan
        cot_multi_data[key] = data
        print(f"[STARTUP] Loaded combined COT: {key} ({len(data)} rows)")
    _populate_single_cot_from_multi("brent")


def _populate_single_cot_from_multi(key):
    """Build the single-dataset cot_data['categories'] (used by the OIES Money
    Positioning analysis and /api/cot/* endpoints) from one commodity's COT."""
    if key not in cot_multi_data:
        return
    df = cot_multi_data[key]
    groups = ["Managed Money", "Producer/Merchant", "Swap Dealer", "Other Reportables",
              "Total Large Traders", "Total Commercial Traders", "Non Reportables"]
    categories = {}
    for grp in groups:
        rows = []
        for _, row in df.iterrows():
            rec = {"date": row["date"].strftime("%Y-%m-%d")}
            lg = row.get(f"{grp}|Long")
            sh = row.get(f"{grp}|Short")
            sp = row.get(f"{grp}|Spread")
            nt = row.get(f"{grp}|Net")
            rec["long"] = float(lg) if pd.notna(lg) else None
            rec["short"] = float(sh) if pd.notna(sh) else None
            rec["spreading"] = float(sp) if pd.notna(sp) else None
            if pd.notna(nt):
                rec["net"] = float(nt)
            elif rec["long"] is not None and rec["short"] is not None:
                rec["net"] = rec["long"] - rec["short"]
            else:
                rec["net"] = None
            rows.append(rec)
        categories[grp] = {
            "data": rows,
            "row_count": len(rows),
            "has_spreading": any(r.get("spreading") is not None for r in rows),
            "headers": ["date", "long", "short", "spreading", "net"],
        }
    cot_data.clear()
    cot_data["categories"] = categories
    cot_data["filename"] = "COT+latest.xlsx"
    cot_data["uploaded_at"] = datetime.utcnow().isoformat()
    # Attach price series (front-month) for CO1/CO2-style price panels
    try:
        pser = {row["date"].strftime("%Y-%m-%d"): (float(row["price"]) if pd.notna(row.get("price")) else None)
                for _, row in df.iterrows()}
        cot_data["price_series"] = pser
    except Exception:
        pass


@app.get("/api/cot_multi/commodities")
async def cot_multi_commodities():
    """List available multi-commodity COT datasets."""
    result = []
    for key in ["brent", "wti", "gasoil", "rbob"]:
        if key in cot_multi_data:
            df = cot_multi_data[key]
            result.append({
                "key": key,
                "label": _COT_MULTI_LABELS.get(key, key),
                "rows": len(df),
                "date_range": [df["date"].min().strftime("%Y-%m-%d"), df["date"].max().strftime("%Y-%m-%d")],
            })
    return {"commodities": result}


@app.get("/api/cot_multi/data")
async def cot_multi_data_endpoint(commodity: str = Query("brent")):
    """Get full COT time series for a commodity."""
    if commodity not in cot_multi_data:
        raise HTTPException(status_code=404, detail=f"No data for '{commodity}'")
    df = cot_multi_data[commodity].copy()
    # Build clean output
    records = []
    for _, row in df.iterrows():
        r = {
            "date": row["date"].strftime("%Y-%m-%d"),
            "price": float(row["price"]) if pd.notna(row.get("price")) else None,
            "mm_long": _gv(row, "Managed Money|Long"),
            "mm_short": _gv(row, "Managed Money|Short"),
            "mm_spread": _gv(row, "Managed Money|Spread"),
            "mm_net": _gv(row, "Managed Money|Net"),
            "or_long": _gv(row, "Other Reportables|Long"),
            "or_short": _gv(row, "Other Reportables|Short"),
            "or_net": _gv(row, "Other Reportables|Net"),
            "tlt_long": _gv(row, "Total Large Traders|Long"),
            "tlt_short": _gv(row, "Total Large Traders|Short"),
            "tlt_net": _gv(row, "Total Large Traders|Net"),
            "pm_long": _gv(row, "Producer/Merchant|Long"),
            "pm_short": _gv(row, "Producer/Merchant|Short"),
            "pm_net": _gv(row, "Producer/Merchant|Net"),
            "sd_long": _gv(row, "Swap Dealer|Long"),
            "sd_short": _gv(row, "Swap Dealer|Short"),
            "sd_net": _gv(row, "Swap Dealer|Net"),
            "tc_long": _gv(row, "Total Commercial Traders|Long"),
            "tc_short": _gv(row, "Total Commercial Traders|Short"),
            "tc_net": _gv(row, "Total Commercial Traders|Net"),
            "nr_long": _gv(row, "Non Reportables|Long"),
            "nr_short": _gv(row, "Non Reportables|Short"),
            "nr_net": _gv(row, "Non Reportables|Net"),
            "oi": _gv(row, "-|Total Open Interest"),
            "mm_pct_oi": _gv(row, "Managed Money|Net as % of Open Interest"),
            "pm_pct_oi": _gv(row, "Producer/Merchant|Net as % of Open Interest"),
            "sd_pct_oi": _gv(row, "Swap Dealer|Net as % of Open Interest"),
            "tlt_pct_oi": _gv(row, "Total Large Traders|Net as % of Open Interest"),
            "tc_pct_oi": _gv(row, "Total Commercial Traders|Net as % of Open Interest"),
        }
        records.append(r)
    return {
        "commodity": commodity,
        "label": _COT_MULTI_LABELS.get(commodity, commodity),
        "count": len(records),
        "data": records,
    }


def _gv(row, col):
    """Get value from row, return None if column missing or NaN."""
    if col in row.index:
        v = row[col]
        if pd.notna(v):
            return round(float(v), 2)
    return None


@app.get("/api/cot_multi/seasonal")
async def cot_multi_seasonal(commodity: str = Query("brent"), field: str = Query("mm_net")):
    """Get seasonal overlay data (by year) for a specific field."""
    if commodity not in cot_multi_data:
        raise HTTPException(status_code=404, detail=f"No data for '{commodity}'")
    df = cot_multi_data[commodity].copy()

    # Map field name to column
    field_col_map = {
        "mm_net": "Managed Money|Net",
        "mm_long": "Managed Money|Long",
        "mm_short": "Managed Money|Short",
        "pm_net": "Producer/Merchant|Net",
        "sd_net": "Swap Dealer|Net",
        "tlt_net": "Total Large Traders|Net",
        "tc_net": "Total Commercial Traders|Net",
        "nr_net": "Non Reportables|Net",
        "oi": "-|Total Open Interest",
        "mm_pct_oi": "Managed Money|Net as % of Open Interest",
    }
    col = field_col_map.get(field)
    if not col or col not in df.columns:
        raise HTTPException(status_code=400, detail=f"Unknown field '{field}'")

    df["year"] = df["date"].dt.year
    df["week"] = df["date"].dt.isocalendar().week.astype(int)
    df["val"] = pd.to_numeric(df[col], errors="coerce")

    years = sorted(df["year"].unique())
    result = {}
    for y in years:
        ydf = df[df["year"] == y][["week", "val"]].dropna()
        result[str(y)] = [{"week": int(r["week"]), "value": round(float(r["val"]), 2)} for _, r in ydf.iterrows()]

    return {"commodity": commodity, "field": field, "years": result}


@app.get("/api/cot_multi/summary")
async def cot_multi_summary(commodity: str = Query("brent")):
    """Summary stats for a commodity's COT data — latest snapshot, percentiles, w/w changes."""
    if commodity not in cot_multi_data:
        raise HTTPException(status_code=404, detail=f"No data for '{commodity}'")
    df = cot_multi_data[commodity].copy()

    fields = {
        "mm_net": "Managed Money|Net",
        "pm_net": "Producer/Merchant|Net",
        "sd_net": "Swap Dealer|Net",
        "or_net": "Other Reportables|Net",
        "tlt_net": "Total Large Traders|Net",
        "tc_net": "Total Commercial Traders|Net",
        "oi": "-|Total Open Interest",
    }

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    prev4 = df.iloc[-4] if len(df) > 4 else latest

    summary = {
        "date": latest["date"].strftime("%Y-%m-%d"),
        "price": float(latest["price"]) if pd.notna(latest.get("price")) else None,
        "price_prev": float(prev["price"]) if pd.notna(prev.get("price")) else None,
        "categories": {},
    }

    for fname, col in fields.items():
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) < 2:
            continue
        val = float(series.iloc[-1])
        val_prev = float(series.iloc[-2])
        val_4w = float(series.iloc[-4]) if len(series) >= 4 else val
        all_vals = series.values
        pctl = float(np.sum(all_vals <= val) / len(all_vals) * 100)
        mean_52 = float(np.mean(all_vals[-52:])) if len(all_vals) >= 52 else float(np.mean(all_vals))
        std_52 = float(np.std(all_vals[-52:])) if len(all_vals) >= 52 else float(np.std(all_vals))
        z = float((val - mean_52) / std_52) if std_52 > 0 else 0.0
        hist_max = float(np.max(all_vals))
        hist_min = float(np.min(all_vals))

        summary["categories"][fname] = {
            "value": round(val, 0),
            "w_change": round(val - val_prev, 0),
            "4w_change": round(val - val_4w, 0),
            "percentile": round(pctl, 1),
            "z_score": round(z, 2),
            "hist_max": round(hist_max, 0),
            "hist_min": round(hist_min, 0),
            "mean_52w": round(mean_52, 0),
        }

    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# ═══  CRUDE BALANCES & MARGINS (Energy Aspects NWE/MED)
# ═══════════════════════════════════════════════════════════════════════════════

ea_bal_data: dict = {}   # {"demand": df, "imports": df, ...}
ea_margins_data: dict = {}  # {"data": df, "regions": [...]}

_EA_BAL_REGION_MAP = {
    "MED": "Mediterranean",
    "NWE": "NW Europe",
}

_EA_MARGINS_SHORT = {
    "Singapore": "Singapore",
    "Mediterranean": "MED",
    "North West Europe": "NWE",
    "US Atlantic Coast": "USAC",
    "US Gulf Coast": "USGC",
    "US Midwest": "USMW",
    "US West Coast": "USWC",
}


@app.on_event("startup")
async def load_ea_bal_margins():
    """Load Energy Aspects crude balance and forward margins data."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    if not os.path.isdir(data_dir):
        data_dir = "/app/data"

    # Crude balance
    bal_path = os.path.join(data_dir, "ea_crude_balance.xlsx")
    if os.path.isfile(bal_path):
        try:
            sheets = ["demand", "exports", "imports", "production", "runs", "statistical_difference", "storage"]
            for s in sheets:
                try:
                    df = pd.read_excel(bal_path, sheet_name=s)
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                    df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
                    # Shorten column names (ensure unique)
                    new_cols = {"Date": "date"}
                    seen = set()
                    for c in df.columns:
                        if c == "Date":
                            continue
                        short = c
                        # Determine region (use "to" destination for imports)
                        region_name = ""
                        if "imports to " in c:
                            if "to Mediterranean" in c:
                                region_name = "MED"
                            elif "to NW Europe" in c:
                                region_name = "NWE"
                        elif "Mediterranean" in c or "MED " in c:
                            region_name = "MED"
                        elif "NW Europe" in c or "NWE " in c:
                            region_name = "NWE"
                        if "NWE balance" in c:
                            short = "NWE"
                        elif "refinery runs in" in c:
                            parts = c.split("refinery runs in ")[-1].split(" in ")[0]
                            short = f"Runs {parts}"
                        elif "stock change" in c and region_name:
                            short = f"{region_name} Stock Change"
                        elif "inventories" in c and region_name:
                            short = f"{region_name} Inventories"
                        elif "imports to " in c and "from " in c and region_name:
                            origin = c.split("from ")[-1].split(" in ")[0]
                            short = f"{region_name} from {origin}"
                        elif "imports to " in c and "from " not in c and region_name:
                            short = f"{region_name} Total"
                        elif region_name:
                            short = region_name
                        # Deduplicate
                        base = short
                        cnt = 2
                        while short in seen:
                            short = f"{base}_{cnt}"
                            cnt += 1
                        seen.add(short)
                        new_cols[c] = short
                    df = df.rename(columns=new_cols)
                    ea_bal_data[s] = df
                except Exception as e:
                    print(f"[EA-BalMarg] Failed sheet {s}: {e}")
            print(f"[STARTUP] Loaded EA crude balance: {list(ea_bal_data.keys())}, {sum(len(v) for v in ea_bal_data.values())} total rows")
        except Exception as e:
            print(f"[STARTUP] Failed EA crude balance: {e}")

    # Forward margins
    margins_path = os.path.join(data_dir, "ea_forward_margins.xlsx")
    if os.path.isfile(margins_path):
        try:
            df = pd.read_excel(margins_path, sheet_name="Data")
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
            # Shorten column names
            new_cols = {"Date": "date"}
            regions = []
            for c in df.columns:
                if c == "Date":
                    continue
                for long_name, short_name in _EA_MARGINS_SHORT.items():
                    if long_name in c:
                        new_cols[c] = short_name
                        regions.append(short_name)
                        break
                else:
                    new_cols[c] = c
            df = df.rename(columns=new_cols)
            for c in df.columns:
                if c != "date":
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            ea_margins_data["df"] = df
            ea_margins_data["regions"] = regions
            print(f"[STARTUP] Loaded EA forward margins: {len(df)} rows, regions: {regions}")
        except Exception as e:
            print(f"[STARTUP] Failed EA forward margins: {e}")


@app.get("/api/ea_bal/sheets")
async def ea_bal_sheets():
    """List available crude balance sheets and their columns."""
    result = {}
    for sheet_name, df in ea_bal_data.items():
        cols = [c for c in df.columns if c != "date"]
        result[sheet_name] = {
            "columns": cols,
            "rows": len(df),
            "date_range": [df["date"].min().strftime("%Y-%m-%d"), df["date"].max().strftime("%Y-%m-%d")],
        }
    return {"sheets": result, "margins_available": bool(ea_margins_data)}


@app.get("/api/ea_bal/data")
async def ea_bal_data_endpoint(sheet: str = Query("demand"), region: str = Query(None)):
    """Get crude balance data for a specific sheet, optionally filtered by region."""
    if sheet not in ea_bal_data:
        raise HTTPException(status_code=404, detail=f"Sheet '{sheet}' not found")
    df = ea_bal_data[sheet].copy()
    cols = [c for c in df.columns if c != "date"]
    if region:
        cols = [c for c in cols if region.upper() in c.upper()]
    if not cols:
        cols = [c for c in df.columns if c != "date"]

    records = []
    for _, row in df.iterrows():
        r = {"date": row["date"].strftime("%Y-%m-%d")}
        for c in cols:
            v = row[c]
            if isinstance(v, pd.Series):
                v = v.iloc[0]
            try:
                r[c] = round(float(v), 2) if pd.notna(v) else None
            except (TypeError, ValueError):
                r[c] = None
        records.append(r)
    return {"sheet": sheet, "columns": cols, "count": len(records), "data": records}


@app.get("/api/ea_margins/data")
async def ea_margins_data_endpoint(region: str = Query(None), period: str = Query("ALL")):
    """Get forward margins data, optionally filtered by region and time period."""
    if "df" not in ea_margins_data:
        raise HTTPException(status_code=404, detail="Forward margins data not loaded")
    df = ea_margins_data["df"].copy()
    regions = ea_margins_data.get("regions", [])

    # Time period filter
    if period != "ALL":
        now = pd.Timestamp.now()
        period_map = {"1Y": 365, "2Y": 730, "3Y": 1095, "5Y": 1825}
        days = period_map.get(period, 99999)
        df = df[df["date"] >= now - pd.Timedelta(days=days)]

    cols = regions
    if region:
        cols = [c for c in regions if region.upper() in c.upper()]
    if not cols:
        cols = regions

    records = []
    for _, row in df.iterrows():
        r = {"date": row["date"].strftime("%Y-%m-%d")}
        for c in cols:
            v = row.get(c)
            r[c] = round(float(v), 2) if pd.notna(v) else None
        records.append(r)
    return {"regions": cols, "count": len(records), "data": records}


@app.get("/api/ea_margins/summary")
async def ea_margins_summary():
    """Summary of latest margins by region."""
    if "df" not in ea_margins_data:
        raise HTTPException(status_code=404, detail="Forward margins data not loaded")
    df = ea_margins_data["df"]
    regions = ea_margins_data.get("regions", [])
    latest = df.dropna(subset=regions, how="all").iloc[-1] if len(df) > 0 else None
    if latest is None:
        return {"regions": []}
    result = []
    for r in regions:
        val = latest.get(r)
        if pd.isna(val):
            continue
        # Get 30d average
        recent = df[r].dropna().tail(30)
        avg_30 = float(recent.mean()) if len(recent) > 0 else None
        prev = df[r].dropna().iloc[-2] if len(df[r].dropna()) > 1 else val
        result.append({
            "region": r,
            "value": round(float(val), 2),
            "change": round(float(val) - float(prev), 2),
            "avg_30d": round(avg_30, 2) if avg_30 is not None else None,
        })
    return {"date": latest["date"].strftime("%Y-%m-%d"), "margins": result}


# ═══════════════════════════════════════════════════════════════════════════════
# ═══  MULTI-TIMEFRAME INSTRUMENTS (Excel with Daily/240/120/60/10 min sheets)
# ═══════════════════════════════════════════════════════════════════════════════

instruments: dict[str, dict] = {}

KNOWN_TIMEFRAMES = ["Daily", "240 min", "120 min", "60 min", "10 min"]


def _parse_instrument_excel(content: bytes, filename: str) -> dict:
    """Parse multi-sheet Excel with timeframe data."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    
    timeframes = {}
    instrument_name = filename.replace(".xlsx", "").replace("+", " ")
    
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if ws.max_row < 2:
            continue
        
        # Normalize timeframe name
        tf_key = sheet_name.strip()
        
        # Read headers from row 1
        headers = []
        for col in range(1, ws.max_column + 1):
            v = ws.cell(row=1, column=col).value
            headers.append(str(v).strip() if v else f"col_{col}")
        
        # Detect columns
        date_col_idx = None
        price_col_idx = None
        volume_col_idx = None
        oi_col_idx = None
        
        for i, h in enumerate(headers):
            hl = h.lower()
            if "date" in hl or "time" in hl:
                date_col_idx = i
            elif "last" in hl or "price" in hl or "close" in hl or "px" in hl:
                price_col_idx = i
            elif "volume" in hl or "vol" in hl:
                volume_col_idx = i
            elif "open interest" in hl or "oi" in hl or "open_interest" in hl:
                oi_col_idx = i
        
        if date_col_idx is None:
            date_col_idx = 0
        if price_col_idx is None and len(headers) > 1:
            price_col_idx = 1
        
        # Extract instrument ticker from header
        if price_col_idx is not None:
            raw_header = headers[price_col_idx]
            # Extract ticker like "CO1 Comdty" or "CON6COQ6 Comdty"
            parts = raw_header.split(" - ")
            if len(parts) > 1:
                instrument_name = parts[0].strip()
        
        # Read data
        rows_data = []
        for row in range(2, ws.max_row + 1):
            date_val = ws.cell(row=row, column=date_col_idx + 1).value
            if date_val is None:
                continue
            
            if isinstance(date_val, datetime):
                date_str = date_val.isoformat()
            else:
                try:
                    date_str = pd.to_datetime(str(date_val)).isoformat()
                except Exception:
                    continue
            
            price_val = None
            if price_col_idx is not None:
                pv = ws.cell(row=row, column=price_col_idx + 1).value
                if pv is not None:
                    try:
                        price_val = float(pv)
                    except (ValueError, TypeError):
                        pass
            
            vol_val = None
            if volume_col_idx is not None:
                vv = ws.cell(row=row, column=volume_col_idx + 1).value
                if vv is not None:
                    try:
                        vol_val = float(vv)
                    except (ValueError, TypeError):
                        pass
            
            oi_val = None
            if oi_col_idx is not None:
                ov = ws.cell(row=row, column=oi_col_idx + 1).value
                if ov is not None:
                    try:
                        oi_val = float(ov)
                    except (ValueError, TypeError):
                        pass
            
            rows_data.append({
                "date": date_str,
                "price": price_val,
                "volume": vol_val,
                "oi": oi_val,
            })
        
        if not rows_data:
            continue
        
        # Sort by date
        rows_data.sort(key=lambda x: x["date"])
        
        has_price = any(r["price"] is not None for r in rows_data)
        has_volume = any(r["volume"] is not None for r in rows_data)
        has_oi = any(r["oi"] is not None for r in rows_data)
        
        timeframes[tf_key] = {
            "data": rows_data,
            "row_count": len(rows_data),
            "has_price": has_price,
            "has_volume": has_volume,
            "has_oi": has_oi,
            "date_range": {"start": rows_data[0]["date"], "end": rows_data[-1]["date"]},
            "headers": headers,
        }
    
    wb.close()
    return {"instrument_name": instrument_name, "timeframes": timeframes}


@app.post("/api/instruments/upload")
async def upload_instrument(file: UploadFile = File(...)):
    """Upload multi-sheet Excel with timeframe data."""
    try:
        content = await file.read()
        parsed = _parse_instrument_excel(content, file.filename or "unknown.xlsx")
        
        inst_id = str(uuid.uuid4())[:8]
        instruments[inst_id] = {
            "id": inst_id,
            "name": parsed["instrument_name"],
            "filename": file.filename,
            "timeframes": parsed["timeframes"],
            "uploaded_at": datetime.utcnow().isoformat(),
        }
        
        tf_summary = {}
        for tf_name, tf_data in parsed["timeframes"].items():
            tf_summary[tf_name] = {
                "row_count": tf_data["row_count"],
                "has_price": tf_data["has_price"],
                "has_volume": tf_data["has_volume"],
                "has_oi": tf_data["has_oi"],
                "date_range": tf_data["date_range"],
            }
        
        return {
            "id": inst_id,
            "name": parsed["instrument_name"],
            "filename": file.filename,
            "timeframes": tf_summary,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse Excel: {str(e)}")


@app.get("/api/instruments")
async def list_instruments():
    result = []
    for inst in instruments.values():
        tf_summary = {}
        for tf_name, tf_data in inst["timeframes"].items():
            tf_summary[tf_name] = {
                "row_count": tf_data["row_count"],
                "has_price": tf_data["has_price"],
                "has_volume": tf_data["has_volume"],
                "has_oi": tf_data["has_oi"],
                "date_range": tf_data["date_range"],
            }
        result.append({
            "id": inst["id"],
            "name": inst["name"],
            "filename": inst.get("filename"),
            "timeframes": tf_summary,
            "uploaded_at": inst["uploaded_at"],
        })
    return result


def _safe_corr(a: np.ndarray, b: np.ndarray):
    """Compute correlation, returning None if NaN/Inf."""
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None
    c = float(np.corrcoef(a, b)[0, 1])
    if np.isnan(c) or np.isinf(c):
        return None
    return round(c, 4)


@app.get("/api/instruments/all-correlations")
async def all_timeframe_correlations(
    inst_id1: str = Query(...), inst_id2: str = Query(...),
):
    """Get correlation summary across all matching timeframes."""
    if inst_id1 not in instruments or inst_id2 not in instruments:
        raise HTTPException(status_code=404, detail="Instrument not found")
    
    inst1 = instruments[inst_id1]
    inst2 = instruments[inst_id2]
    
    summary = []
    
    for tf1_name, tf1_data in inst1["timeframes"].items():
        for tf2_name, tf2_data in inst2["timeframes"].items():
            if tf1_name.strip().lower() != tf2_name.strip().lower():
                continue
            
            df1 = pd.DataFrame(tf1_data["data"])
            df2 = pd.DataFrame(tf2_data["data"])
            
            df1["date_key"] = pd.to_datetime(df1["date"]).dt.floor("min")
            df2["date_key"] = pd.to_datetime(df2["date"]).dt.floor("min")
            
            merged = pd.merge(df1[["date_key", "price"]], df2[["date_key", "price"]],
                             on="date_key", suffixes=("_1", "_2"), how="inner")
            merged = merged.dropna(subset=["price_1", "price_2"])
            
            if len(merged) < 5:
                continue
            
            p1 = merged["price_1"].values.astype(float)
            p2 = merged["price_2"].values.astype(float)
            
            corr = _safe_corr(p1, p2)
            
            # Returns correlation
            ret1 = np.diff(p1) / np.where(p1[:-1] == 0, 1e-10, p1[:-1])
            ret2 = np.diff(p2) / np.where(p2[:-1] == 0, 1e-10, p2[:-1])
            ret_corr = _safe_corr(ret1, ret2)
            
            # Recent vs historical
            recent_n = min(20, len(p1) // 3)
            if recent_n > 5:
                recent_corr = _safe_corr(p1[-recent_n:], p2[-recent_n:])
                hist_corr = _safe_corr(p1[:-recent_n], p2[:-recent_n]) if len(p1) > recent_n + 5 else None
            else:
                recent_corr = None
                hist_corr = None
            
            summary.append({
                "timeframe": tf1_name.strip(),
                "price_correlation": corr,
                "returns_correlation": ret_corr,
                "recent_correlation": recent_corr,
                "historical_correlation": hist_corr,
                "data_points": len(merged),
            })
    
    return {
        "instrument1": {"id": inst_id1, "name": inst1["name"]},
        "instrument2": {"id": inst_id2, "name": inst2["name"]},
        "timeframe_correlations": summary,
    }


@app.get("/api/instruments/{inst_id}")
async def get_instrument(inst_id: str, timeframe: str = Query(default="Daily")):
    if inst_id not in instruments:
        raise HTTPException(status_code=404, detail="Instrument not found")
    inst = instruments[inst_id]
    
    # Find matching timeframe (case-insensitive, trimmed)
    tf_data = None
    tf_key = None
    for k, v in inst["timeframes"].items():
        if k.strip().lower() == timeframe.strip().lower():
            tf_data = v
            tf_key = k
            break
    
    if tf_data is None:
        # Return first available
        tf_key = list(inst["timeframes"].keys())[0]
        tf_data = inst["timeframes"][tf_key]
    
    return {
        "id": inst_id,
        "name": inst["name"],
        "timeframe": tf_key,
        "available_timeframes": list(inst["timeframes"].keys()),
        "data": tf_data["data"],
        "row_count": tf_data["row_count"],
        "has_price": tf_data["has_price"],
        "has_volume": tf_data["has_volume"],
        "has_oi": tf_data["has_oi"],
        "date_range": tf_data["date_range"],
    }


@app.delete("/api/instruments/{inst_id}")
async def delete_instrument(inst_id: str):
    if inst_id not in instruments:
        raise HTTPException(status_code=404, detail="Instrument not found")
    del instruments[inst_id]
    return {"status": "deleted"}


def _build_features(prices: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Build technical features for ML models."""
    n = len(prices)
    features = []
    names = []
    
    # Returns
    ret1 = np.zeros(n)
    denom = np.where(prices[:-1] == 0, 1e-10, prices[:-1])
    ret1[1:] = (prices[1:] - prices[:-1]) / denom * 100
    ret1 = np.where(np.isfinite(ret1), ret1, 0.0)
    features.append(ret1)
    names.append("ret_1")
    
    # Multi-period returns
    for p in [3, 5, 10]:
        ret = np.zeros(n)
        for i in range(p, n):
            d = prices[i - p] if prices[i - p] != 0 else 1e-10
            ret[i] = (prices[i] - prices[i - p]) / d * 100
            if not np.isfinite(ret[i]):
                ret[i] = 0.0
        features.append(ret)
        names.append(f"ret_{p}")
    
    # Moving averages ratios
    for w in [5, 10, 20]:
        ma = np.zeros(n)
        for i in range(w, n):
            ma[i] = np.mean(prices[i - w:i])
        ratio = np.zeros(n)
        for i in range(w, n):
            if ma[i] > 0:
                ratio[i] = prices[i] / ma[i] - 1
        features.append(ratio)
        names.append(f"ma_ratio_{w}")
    
    # Volatility
    for w in [5, 10, 20]:
        vol = np.zeros(n)
        for i in range(w, n):
            vol[i] = np.std(ret1[i - w + 1:i + 1])
        features.append(vol)
        names.append(f"vol_{w}")
    
    # RSI
    rsi_vals = np.full(n, 50.0)
    period = 14
    for i in range(period + 1, n):
        gains = []
        losses = []
        for j in range(i - period, i):
            d = ret1[j]
            if d > 0:
                gains.append(d)
            else:
                losses.append(abs(d))
        avg_g = np.mean(gains) if gains else 0
        avg_l = np.mean(losses) if losses else 0.001
        rs = avg_g / avg_l if avg_l > 0 else 100
        rsi_vals[i] = 100 - 100 / (1 + rs)
    features.append(rsi_vals)
    names.append("rsi")
    
    # Momentum
    for p in [5, 10]:
        mom = np.zeros(n)
        for i in range(p, n):
            mom[i] = prices[i] - prices[i - p]
        features.append(mom)
        names.append(f"momentum_{p}")
    
    return np.column_stack(features), names


def _run_strategy(prices: np.ndarray, dates: list, signals: np.ndarray,
                  strategy_name: str, description: str) -> dict:
    """Run a backtest on given signals and return comprehensive results."""
    n = len(prices)
    if n < 5:
        return {"name": strategy_name, "error": "Insufficient data"}
    
    # Calculate PnL
    position = 0.0
    pnl_series = []
    cum_pnl = 0.0
    equity = [0.0]
    trades = []
    entry_price = 0.0
    wins = 0
    losses = 0
    total_trades = 0
    
    for i in range(1, n):
        daily_pnl = position * (prices[i] - prices[i - 1])
        cum_pnl += daily_pnl
        
        target = float(signals[i]) if i < len(signals) else 0.0
        if np.isnan(target):
            target = 0.0
        target = max(-1.0, min(1.0, target))
        
        if target != position:
            # Close existing
            if position != 0 and entry_price != 0:
                trade_pnl = position * (prices[i] - entry_price)
                if trade_pnl > 0:
                    wins += 1
                else:
                    losses += 1
                total_trades += 1
            
            if target != 0:
                entry_price = prices[i]
            position = target
        
        pnl_series.append(daily_pnl)
        equity.append(cum_pnl)
    
    # Close final position
    if position != 0 and entry_price != 0:
        trade_pnl = position * (prices[-1] - entry_price)
        if trade_pnl > 0:
            wins += 1
        else:
            losses += 1
        total_trades += 1
    
    pnl_arr = np.array(pnl_series)
    equity_arr = np.array(equity)
    
    # Stats
    total_return = cum_pnl
    if len(pnl_arr) > 1 and np.std(pnl_arr) > 0:
        sharpe = float(np.mean(pnl_arr) / np.std(pnl_arr) * np.sqrt(252))
    else:
        sharpe = 0.0
    
    # Max drawdown
    peak = np.maximum.accumulate(equity_arr)
    dd = equity_arr - peak
    max_dd = float(np.min(dd)) if len(dd) > 0 else 0.0
    
    win_rate = wins / total_trades * 100 if total_trades > 0 else 0.0
    
    # Current signal
    current_signal = float(signals[-1]) if len(signals) > 0 else 0.0
    if np.isnan(current_signal):
        current_signal = 0.0
    
    if current_signal > 0.3:
        recommendation = "LONG"
    elif current_signal < -0.3:
        recommendation = "SHORT"
    else:
        recommendation = "NEUTRAL"
    
    # Build summary paragraph
    perf_word = "profitable" if total_return > 0 else "unprofitable"
    summary = (
        f"The {strategy_name} strategy applied to this instrument has been {perf_word} "
        f"over the analyzed period, generating a total return of {total_return:.2f} points "
        f"with a Sharpe ratio of {sharpe:.2f}. "
        f"The strategy executed {total_trades} trades with a win rate of {win_rate:.1f}%. "
        f"Maximum drawdown was {max_dd:.2f} points. "
    )
    
    if recommendation == "LONG":
        summary += (
            f"The current signal is BULLISH — the model suggests going LONG. "
            f"{description}"
        )
    elif recommendation == "SHORT":
        summary += (
            f"The current signal is BEARISH — the model suggests going SHORT. "
            f"{description}"
        )
    else:
        summary += (
            f"The current signal is NEUTRAL — no clear directional bias. "
            f"It is recommended to STAY FLAT and wait for a clearer setup. "
            f"{description}"
        )
    
    # Equity curve for chart (sample if too many points)
    eq_data = []
    step = max(1, len(equity) // 300)
    for i in range(0, len(equity), step):
        d = dates[i] if i < len(dates) else ""
        eq_data.append({"date": d, "equity": round(equity[i], 4)})
    
    # Signal overlay data
    sig_data = []
    for i in range(0, n, step):
        d = dates[i] if i < len(dates) else ""
        sig_data.append({
            "date": d,
            "price": round(float(prices[i]), 4),
            "signal": round(float(signals[i]), 2) if i < len(signals) and not np.isnan(signals[i]) else 0,
        })
    
    return {
        "name": strategy_name,
        "description": description,
        "total_return": round(total_return, 4),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "win_rate": round(win_rate, 2),
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "recommendation": recommendation,
        "current_signal": round(current_signal, 2),
        "summary": summary,
        "equity_curve": eq_data,
        "signal_data": sig_data,
    }


@app.get("/api/instruments/{inst_id}/analytics")
async def get_instrument_analytics(inst_id: str, timeframe: str = Query(default="Daily")):
    """Comprehensive analytics for a specific timeframe."""
    if inst_id not in instruments:
        raise HTTPException(status_code=404, detail="Instrument not found")
    inst = instruments[inst_id]
    
    tf_data = None
    tf_key = None
    for k, v in inst["timeframes"].items():
        if k.strip().lower() == timeframe.strip().lower():
            tf_data = v
            tf_key = k
            break
    if tf_data is None:
        raise HTTPException(status_code=404, detail=f"Timeframe '{timeframe}' not found")
    
    data = tf_data["data"]
    prices = np.array([r["price"] for r in data if r["price"] is not None], dtype=float)
    volumes = np.array([r["volume"] for r in data if r["volume"] is not None], dtype=float)
    dates = [r["date"] for r in data if r["price"] is not None]
    
    if len(prices) < 5:
        raise HTTPException(status_code=400, detail="Not enough price data for analytics")
    
    # Basic stats
    denom = np.where(prices[:-1] == 0, 1e-10, prices[:-1])
    returns = np.diff(prices) / denom * 100
    returns = np.where(np.isfinite(returns), returns, 0.0)
    
    stats = {
        "current_price": round(float(prices[-1]), 4),
        "prev_price": round(float(prices[-2]), 4) if len(prices) > 1 else None,
        "change": round(float(prices[-1] - prices[-2]), 4) if len(prices) > 1 else 0,
        "change_pct": round(float(returns[-1]), 4) if len(returns) > 0 else 0,
        "high": round(float(np.max(prices)), 4),
        "low": round(float(np.min(prices)), 4),
        "mean": round(float(np.mean(prices)), 4),
        "std": round(float(np.std(prices)), 4),
        "data_points": len(prices),
    }
    
    if len(returns) > 1:
        stats["volatility_ann"] = round(float(np.std(returns) * np.sqrt(252)), 4)
        stats["avg_return"] = round(float(np.mean(returns)), 4)
        stats["skewness"] = round(float(pd.Series(returns).skew()), 4)
        stats["kurtosis"] = round(float(pd.Series(returns).kurtosis()), 4)
    
    if len(volumes) > 0:
        stats["avg_volume"] = round(float(np.mean(volumes)), 0)
        stats["total_volume"] = round(float(np.sum(volumes)), 0)
    
    # Moving averages
    ma_data = []
    step = max(1, len(prices) // 300)
    for i in range(0, len(prices), step):
        row = {"date": dates[i], "price": round(float(prices[i]), 4)}
        for w in [5, 10, 20, 50]:
            if i >= w:
                row[f"sma_{w}"] = round(float(np.mean(prices[i - w:i])), 4)
        ma_data.append(row)
    
    # RSI
    rsi_data = []
    period = 14
    for i in range(period + 1, len(prices), step):
        gains, losses_arr = [], []
        for j in range(i - period, i):
            d = returns[j] if j < len(returns) else 0
            if d > 0:
                gains.append(d)
            else:
                losses_arr.append(abs(d))
        avg_g = np.mean(gains) if gains else 0
        avg_l = np.mean(losses_arr) if losses_arr else 0.001
        rs = avg_g / avg_l
        rsi = 100 - 100 / (1 + rs)
        rsi_data.append({"date": dates[i], "rsi": round(rsi, 2)})
    
    # Bollinger Bands
    bb_data = []
    bb_period = 20
    for i in range(bb_period, len(prices), step):
        window = prices[i - bb_period:i]
        ma = float(np.mean(window))
        std = float(np.std(window))
        bb_data.append({
            "date": dates[i],
            "price": round(float(prices[i]), 4),
            "upper": round(ma + 2 * std, 4),
            "middle": round(ma, 4),
            "lower": round(ma - 2 * std, 4),
        })
    
    # MACD
    macd_data = []
    if len(prices) > 26:
        ema12 = pd.Series(prices).ewm(span=12).mean().values
        ema26 = pd.Series(prices).ewm(span=26).mean().values
        macd_line = ema12 - ema26
        signal_line = pd.Series(macd_line).ewm(span=9).mean().values
        histogram = macd_line - signal_line
        
        for i in range(26, len(prices), step):
            macd_data.append({
                "date": dates[i],
                "macd": round(float(macd_line[i]), 4),
                "signal": round(float(signal_line[i]), 4),
                "histogram": round(float(histogram[i]), 4),
            })
    
    # Returns distribution
    if len(returns) > 10:
        clean_returns = returns[np.isfinite(returns)]
        if len(clean_returns) > 10:
            hist_vals, bin_edges = np.histogram(clean_returns, bins=30)
        else:
            hist_vals, bin_edges = np.array([]), np.array([])
        returns_dist = []
        for i in range(len(hist_vals)):
            returns_dist.append({
                "bin": round(float((bin_edges[i] + bin_edges[i + 1]) / 2), 3),
                "count": int(hist_vals[i]),
            })
    else:
        returns_dist = []
    if not returns_dist:
        returns_dist = []
    
    # Volume profile
    vol_data = []
    if len(volumes) > 0:
        for i in range(0, len(data), step):
            if data[i]["volume"] is not None and data[i]["price"] is not None:
                vol_data.append({
                    "date": data[i]["date"],
                    "volume": data[i]["volume"],
                    "price": data[i]["price"],
                })
    
    # Support/Resistance levels
    support_resistance = []
    if len(prices) > 20:
        # Simple pivot points
        recent = prices[-20:]
        pivot = (float(np.max(recent)) + float(np.min(recent)) + float(recent[-1])) / 3
        r1 = 2 * pivot - float(np.min(recent))
        s1 = 2 * pivot - float(np.max(recent))
        r2 = pivot + (float(np.max(recent)) - float(np.min(recent)))
        s2 = pivot - (float(np.max(recent)) - float(np.min(recent)))
        support_resistance = [
            {"level": round(r2, 4), "type": "R2"},
            {"level": round(r1, 4), "type": "R1"},
            {"level": round(pivot, 4), "type": "Pivot"},
            {"level": round(s1, 4), "type": "S1"},
            {"level": round(s2, 4), "type": "S2"},
        ]
    
    return {
        "id": inst_id,
        "name": inst["name"],
        "timeframe": tf_key,
        "stats": stats,
        "ma_data": ma_data,
        "rsi_data": rsi_data,
        "bb_data": bb_data,
        "macd_data": macd_data,
        "returns_distribution": returns_dist,
        "volume_data": vol_data,
        "support_resistance": support_resistance,
    }


@app.post("/api/instruments/cross-correlation")
async def cross_instrument_correlation(
    inst_id1: str = Query(...), inst_id2: str = Query(...),
    timeframe: str = Query(default="Daily"),
):
    """Compute correlation between two instruments across timeframes."""
    if inst_id1 not in instruments:
        raise HTTPException(status_code=404, detail=f"Instrument {inst_id1} not found")
    if inst_id2 not in instruments:
        raise HTTPException(status_code=404, detail=f"Instrument {inst_id2} not found")
    
    inst1 = instruments[inst_id1]
    inst2 = instruments[inst_id2]
    
    results = {}
    
    # If specific timeframe requested, just do that one
    tfs_to_check = [timeframe] if timeframe != "all" else list(set(
        list(inst1["timeframes"].keys()) + list(inst2["timeframes"].keys())
    ))
    
    for tf in tfs_to_check:
        tf1_data = None
        tf2_data = None
        for k, v in inst1["timeframes"].items():
            if k.strip().lower() == tf.strip().lower():
                tf1_data = v
                break
        for k, v in inst2["timeframes"].items():
            if k.strip().lower() == tf.strip().lower():
                tf2_data = v
                break
        
        if tf1_data is None or tf2_data is None:
            results[tf] = {"error": "Timeframe not available in both instruments"}
            continue
        
        # Build DataFrames and merge on date
        df1 = pd.DataFrame(tf1_data["data"])
        df2 = pd.DataFrame(tf2_data["data"])
        
        # Truncate dates to match precision
        df1["date_key"] = pd.to_datetime(df1["date"]).dt.floor("min")
        df2["date_key"] = pd.to_datetime(df2["date"]).dt.floor("min")
        
        merged = pd.merge(df1[["date_key", "price"]], df2[["date_key", "price"]],
                         on="date_key", suffixes=("_1", "_2"), how="inner")
        merged = merged.dropna(subset=["price_1", "price_2"])
        
        if len(merged) < 5:
            results[tf] = {"error": "Not enough overlapping data", "n": len(merged)}
            continue
        
        p1 = merged["price_1"].values.astype(float)
        p2 = merged["price_2"].values.astype(float)
        dates_merged = merged["date_key"].dt.strftime("%Y-%m-%d %H:%M").tolist()
        
        # Overall correlation
        corr = _safe_corr(p1, p2)
        corr_val = corr if corr is not None else 0
        r_sq = corr_val ** 2
        
        # Returns correlation
        ret1 = np.diff(p1) / np.where(p1[:-1] == 0, 1e-10, p1[:-1])
        ret2 = np.diff(p2) / np.where(p2[:-1] == 0, 1e-10, p2[:-1])
        ret_corr = _safe_corr(ret1, ret2)
        
        # Rolling correlation windows
        rolling_windows = {"5": 5, "10": 10, "20": 20, "50": 50}
        rolling_corrs = {}
        
        for wname, wsize in rolling_windows.items():
            if len(p1) < wsize + 1:
                continue
            rc_data = []
            r1 = np.diff(p1) / np.where(p1[:-1] == 0, 1e-10, p1[:-1])
            r2 = np.diff(p2) / np.where(p2[:-1] == 0, 1e-10, p2[:-1])
            for i in range(wsize, len(r1)):
                w1 = r1[i - wsize:i]
                w2 = r2[i - wsize:i]
                rc = _safe_corr(w1, w2)
                rc_data.append({
                    "date": dates_merged[i + 1] if i + 1 < len(dates_merged) else "",
                    "correlation": rc,
                })
            rolling_corrs[f"rolling_{wname}"] = rc_data
        
        # Scatter data (sampled)
        scatter = []
        sample_step = max(1, len(p1) // 200)
        for i in range(0, len(p1), sample_step):
            scatter.append({
                "x": round(float(p1[i]), 4),
                "y": round(float(p2[i]), 4),
                "date": dates_merged[i],
            })
        
        # Regression
        try:
            slope, intercept = np.polyfit(p1, p2, 1)
        except Exception:
            slope, intercept = 0.0, 0.0
        
        results[tf] = {
            "correlation": corr,
            "r_squared": round(r_sq, 4),
            "returns_correlation": ret_corr,
            "n": len(merged),
            "scatter": scatter,
            "rolling_correlations": rolling_corrs,
            "regression": {"slope": round(float(slope), 6), "intercept": round(float(intercept), 4)},
            "stats": {
                "mean_1": round(float(np.mean(p1)), 4),
                "mean_2": round(float(np.mean(p2)), 4),
                "std_1": round(float(np.std(p1)), 4),
                "std_2": round(float(np.std(p2)), 4),
            },
        }
    
    return {
        "instrument1": {"id": inst_id1, "name": inst1["name"]},
        "instrument2": {"id": inst_id2, "name": inst2["name"]},
        "results": results,
    }


@app.get("/api/instruments/{inst_id}/strategies")
async def run_all_strategies(inst_id: str, timeframe: str = Query(default="Daily")):
    """Run all 8 trading strategies on an instrument timeframe."""
    if inst_id not in instruments:
        raise HTTPException(status_code=404, detail="Instrument not found")
    inst = instruments[inst_id]
    
    tf_data = None
    tf_key = None
    for k, v in inst["timeframes"].items():
        if k.strip().lower() == timeframe.strip().lower():
            tf_data = v
            tf_key = k
            break
    if tf_data is None:
        raise HTTPException(status_code=404, detail=f"Timeframe '{timeframe}' not found")
    
    data = tf_data["data"]
    prices = np.array([r["price"] for r in data if r["price"] is not None], dtype=float)
    dates = [r["date"][:16] for r in data if r["price"] is not None]
    
    if len(prices) < 30:
        raise HTTPException(status_code=400, detail="Need at least 30 data points for strategies")
    
    n = len(prices)
    strategies = []
    
    # ──── Strategy 1: MA Crossover (SMA 10/30) ────
    fast_w, slow_w = 10, 30
    if n > slow_w:
        sma_fast = pd.Series(prices).rolling(fast_w).mean().values
        sma_slow = pd.Series(prices).rolling(slow_w).mean().values
        sig = np.zeros(n)
        for i in range(slow_w, n):
            if sma_fast[i] > sma_slow[i]:
                sig[i] = 1.0
            elif sma_fast[i] < sma_slow[i]:
                sig[i] = -1.0
        strategies.append(_run_strategy(prices, dates, sig, "MA Crossover (10/30)",
            "This trend-following strategy uses 10 and 30-period simple moving average crossovers "
            "to capture directional momentum. It works best in trending markets but may whipsaw in ranges."))
    
    # ──── Strategy 2: RSI Mean Reversion ────
    period = 14
    if n > period + 1:
        sig = np.zeros(n)
        for i in range(period + 1, n):
            gains, loss_arr = [], []
            for j in range(i - period, i):
                d = (prices[j] - prices[j - 1]) / prices[j - 1] * 100 if j > 0 else 0
                if d > 0:
                    gains.append(d)
                else:
                    loss_arr.append(abs(d))
            avg_g = np.mean(gains) if gains else 0
            avg_l = np.mean(loss_arr) if loss_arr else 0.001
            rsi = 100 - 100 / (1 + avg_g / avg_l)
            if rsi < 30:
                sig[i] = 1.0
            elif rsi > 70:
                sig[i] = -1.0
            else:
                sig[i] = sig[i - 1] * 0.95
        strategies.append(_run_strategy(prices, dates, sig, "RSI Mean Reversion (14)",
            "A counter-trend strategy that buys when RSI drops below 30 (oversold) and sells when "
            "RSI rises above 70 (overbought). Effective in range-bound markets with clear oscillation."))
    
    # ──── Strategy 3: Bollinger Band Breakout ────
    bb_period = 20
    if n > bb_period:
        sig = np.zeros(n)
        ma = pd.Series(prices).rolling(bb_period).mean().values
        std = pd.Series(prices).rolling(bb_period).std().values
        for i in range(bb_period, n):
            upper = ma[i] + 2 * std[i]
            lower = ma[i] - 2 * std[i]
            if prices[i] < lower:
                sig[i] = 1.0
            elif prices[i] > upper:
                sig[i] = -1.0
            else:
                if sig[i - 1] == 1.0 and prices[i] < ma[i]:
                    sig[i] = 1.0
                elif sig[i - 1] == -1.0 and prices[i] > ma[i]:
                    sig[i] = -1.0
        strategies.append(_run_strategy(prices, dates, sig, "Bollinger Band Reversion",
            "Trades mean reversion within Bollinger Bands (20-period, 2 std). "
            "Enters long at lower band, short at upper band, exits at the mean. "
            "Best suited for instruments with regular volatility cycles."))
    
    # ──── Strategy 4: Z-Score Mean Reversion ────
    z_lookback = 20
    if n > z_lookback:
        sig = np.zeros(n)
        for i in range(z_lookback, n):
            window = prices[i - z_lookback:i]
            z = (prices[i] - np.mean(window)) / (np.std(window) + 1e-10)
            if z < -2.0:
                sig[i] = 1.0
            elif z > 2.0:
                sig[i] = -1.0
            elif abs(z) < 0.5:
                sig[i] = 0.0
            else:
                sig[i] = sig[i - 1]
        strategies.append(_run_strategy(prices, dates, sig, "Z-Score Mean Reversion",
            "A statistical arbitrage strategy using z-score normalization over 20 periods. "
            "Enters when price deviates >2 standard deviations from mean, exits at 0.5 std. "
            "Ideal for spread trading and mean-reverting instruments."))
    
    # ──── Strategy 5: MACD Momentum ────
    if n > 35:
        ema12 = pd.Series(prices).ewm(span=12).mean().values
        ema26 = pd.Series(prices).ewm(span=26).mean().values
        macd_line = ema12 - ema26
        signal_line = pd.Series(macd_line).ewm(span=9).mean().values
        sig = np.zeros(n)
        for i in range(35, n):
            if macd_line[i] > signal_line[i] and macd_line[i - 1] <= signal_line[i - 1]:
                sig[i] = 1.0
            elif macd_line[i] < signal_line[i] and macd_line[i - 1] >= signal_line[i - 1]:
                sig[i] = -1.0
            else:
                sig[i] = sig[i - 1]
        strategies.append(_run_strategy(prices, dates, sig, "MACD Momentum (12/26/9)",
            "Trades MACD crossovers — goes long when MACD crosses above signal line, "
            "short when it crosses below. A classic momentum indicator that captures "
            "trend changes with moderate lag. Works well on daily and 240-min timeframes."))
    
    # ──── Strategy 6: Ichimoku Cloud ────
    if n > 52:
        tenkan = np.zeros(n)
        kijun = np.zeros(n)
        for i in range(52, n):
            tenkan[i] = (np.max(prices[i - 9:i + 1]) + np.min(prices[i - 9:i + 1])) / 2
            kijun[i] = (np.max(prices[i - 26:i + 1]) + np.min(prices[i - 26:i + 1])) / 2
        
        senkou_a = (tenkan + kijun) / 2
        senkou_b = np.zeros(n)
        for i in range(52, n):
            senkou_b[i] = (np.max(prices[i - 52:i + 1]) + np.min(prices[i - 52:i + 1])) / 2
        
        sig = np.zeros(n)
        for i in range(52, n):
            cloud_top = max(senkou_a[i], senkou_b[i])
            cloud_bottom = min(senkou_a[i], senkou_b[i])
            if prices[i] > cloud_top and tenkan[i] > kijun[i]:
                sig[i] = 1.0
            elif prices[i] < cloud_bottom and tenkan[i] < kijun[i]:
                sig[i] = -1.0
            else:
                sig[i] = sig[i - 1] * 0.9
        strategies.append(_run_strategy(prices, dates, sig, "Ichimoku Cloud",
            "Uses the Ichimoku Kinko Hyo system with Tenkan-sen (9), Kijun-sen (26), "
            "and Senkou Span (52) to determine trend direction and support/resistance. "
            "Generates strong signals when price and conversion line align above/below the cloud."))
    
    # ──── Strategy 7: Random Forest ML ────
    if n > 60:
        try:
            X, feature_names = _build_features(prices)
            # Target: next-period return direction
            y = np.zeros(n)
            for i in range(n - 1):
                y[i] = 1 if prices[i + 1] > prices[i] else -1
            y[-1] = 0
            
            # Walk-forward: train on first 70%, predict rest
            train_end = int(n * 0.7)
            valid_mask = np.all(np.isfinite(X), axis=1) & (np.arange(n) >= 20)
            
            train_mask = valid_mask.copy()
            train_mask[train_end:] = False
            
            if np.sum(train_mask) > 30:
                _ensure_sklearn()
                scaler = StandardScaler()
                X_train = scaler.fit_transform(X[train_mask])
                y_train = y[train_mask]
                
                rf = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
                rf.fit(X_train, y_train)
                
                sig = np.zeros(n)
                for i in range(train_end, n):
                    if valid_mask[i]:
                        x_pred = scaler.transform(X[i:i + 1])
                        prob = rf.predict_proba(x_pred)[0]
                        classes = rf.classes_
                        long_prob = prob[list(classes).index(1)] if 1 in classes else 0
                        short_prob = prob[list(classes).index(-1)] if -1 in classes else 0
                        sig[i] = long_prob - short_prob
                    else:
                        sig[i] = sig[i - 1] if i > 0 else 0
                
                # Feature importance
                importances = dict(zip(feature_names, [round(float(x), 4) for x in rf.feature_importances_]))
                
                result = _run_strategy(prices, dates, sig, "Random Forest ML",
                    "A machine learning strategy using Random Forest classification with technical features "
                    "(returns, moving average ratios, volatility, RSI, momentum). "
                    "Walk-forward validated: trained on 70% of data, tested on remaining 30%. "
                    "Adapts to non-linear patterns that traditional indicators may miss.")
                result["feature_importance"] = importances
                strategies.append(result)
        except Exception as e:
            strategies.append({"name": "Random Forest ML", "error": str(e)})
    
    # ──── Strategy 8: Gradient Boosting ML ────
    if n > 60:
        try:
            X, feature_names = _build_features(prices)
            y = np.zeros(n)
            for i in range(n - 1):
                y[i] = 1 if prices[i + 1] > prices[i] else -1
            y[-1] = 0
            
            train_end = int(n * 0.7)
            valid_mask = np.all(np.isfinite(X), axis=1) & (np.arange(n) >= 20)
            
            train_mask = valid_mask.copy()
            train_mask[train_end:] = False
            
            if np.sum(train_mask) > 30:
                _ensure_sklearn()
                scaler = StandardScaler()
                X_train = scaler.fit_transform(X[train_mask])
                y_train = y[train_mask]
                
                gb = GradientBoostingClassifier(
                    n_estimators=150, max_depth=4, learning_rate=0.05, random_state=42
                )
                gb.fit(X_train, y_train)
                
                sig = np.zeros(n)
                for i in range(train_end, n):
                    if valid_mask[i]:
                        x_pred = scaler.transform(X[i:i + 1])
                        prob = gb.predict_proba(x_pred)[0]
                        classes = gb.classes_
                        long_prob = prob[list(classes).index(1)] if 1 in classes else 0
                        short_prob = prob[list(classes).index(-1)] if -1 in classes else 0
                        sig[i] = long_prob - short_prob
                    else:
                        sig[i] = sig[i - 1] if i > 0 else 0
                
                importances = dict(zip(feature_names, [round(float(x), 4) for x in gb.feature_importances_]))
                
                result = _run_strategy(prices, dates, sig, "Gradient Boosting ML",
                    "An advanced ML strategy using Gradient Boosting (XGBoost-style) ensemble learning. "
                    "Sequentially builds decision trees that correct previous errors, capturing complex "
                    "non-linear relationships in price dynamics. Walk-forward validated on 30% out-of-sample data. "
                    "Generally more robust than Random Forest for financial time series with regime changes.")
                result["feature_importance"] = importances
                strategies.append(result)
        except Exception as e:
            strategies.append({"name": "Gradient Boosting ML", "error": str(e)})
    
    return {
        "id": inst_id,
        "name": inst["name"],
        "timeframe": tf_key,
        "data_points": n,
        "strategies": strategies,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EIA BALANCES TAB - Weekly Petroleum Supply/Demand/Stocks
# ═══════════════════════════════════════════════════════════════════════════════

eia_data_store: dict = {}

EIA_PRODUCTS = {
    "crude_oil": {
        "name": "Crude Oil",
        "supply": {"WCRFPUS2": "Field Production", "WCRIMUS2": "Imports"},
        "disposition": {"WCRRIUS2": "Refinery Net Input", "WCREXUS2": "Exports"},
        "stocks": {"WCRSTUS1": "Total Stocks (incl SPR)", "WCESTUS1": "Stocks excl SPR", "WCSSTUS1": "SPR Stocks", "W_EPC0_SAX_NUS_MBBL": "Stocks excl SPR incl Lease"},
        "product_supplied": {},
        "other": {"WGIRIUS2": "Gross Inputs into Refineries", "WPULEUS3": "Refinery Utilization %", "WOCLEUS2": "Operable Distillation Capacity"},
    },
    "gasoline": {
        "name": "Motor Gasoline",
        "supply": {"WGFRPUS2": "Finished Motor Gasoline Production", "W_EPM0F_YPR_NUS_MBBLD": "Net Production (Finished)", "WGRRPUS2": "Reformulated Production", "WGCRPUS2": "Conventional Production", "W_EPOOXE_YIR_NUS_MBBLD": "Fuel Ethanol Input"},
        "disposition": {"WGTIMUS2": "Total Imports", "WGFIMUS2": "Finished Imports", "W_EPM0F_EEX_NUS_MBBLD": "Finished Exports"},
        "stocks": {"WGTSTUS1": "Total Stocks", "WGFSTUS1": "Finished Stocks", "WGRSTUS1": "Reformulated Stocks", "WGCSTUS1": "Conventional Stocks", "WBCSTUS1": "Blending Components Stocks"},
        "product_supplied": {"WGFUPUS2": "Product Supplied"},
        "other": {"W_EPM0_VSD_NUS_DAYS": "Days of Supply"},
    },
    "distillate": {
        "name": "Distillate Fuel Oil",
        "supply": {"WDIRPUS2": "Net Production", "WD0TP_NUS_2": "Production 0-15 ppm Sulfur", "WDGRPUS2": "Production >500 ppm Sulfur"},
        "disposition": {"WDIIMUS2": "Imports", "WDIEXUS2": "Exports"},
        "stocks": {"WDISTUS1": "Total Stocks", "WD0ST_NUS_1": "Stocks 0-15 ppm Sulfur", "WDGSTUS1": "Stocks >500 ppm Sulfur"},
        "product_supplied": {"WDIUPUS2": "Product Supplied"},
        "other": {"W_EPD0_VSD_NUS_DAYS": "Days of Supply"},
    },
    "jet_fuel": {
        "name": "Jet Fuel (Kerosene-Type)",
        "supply": {"WKJRPUS2": "Net Production"},
        "disposition": {"WKJIMUS2": "Imports", "WKJEXUS2": "Exports"},
        "stocks": {"WKJSTUS1": "Ending Stocks"},
        "product_supplied": {"WKJUPUS2": "Product Supplied"},
        "other": {"W_EPJK_VSD_NUS_DAYS": "Days of Supply"},
    },
    "propane": {
        "name": "Propane/Propylene",
        "supply": {"WPRTP_NUS_2": "Net Production"},
        "disposition": {"WPRIM_NUS-Z00_2": "Imports", "W_EPLLPZ_EEX_NUS-Z00_MBBLD": "Exports"},
        "stocks": {"WPRSTUS1": "Ending Stocks excl Propylene", "W_EPLLPZ_SAE_NUS_MBBL": "Total Propane/Propylene Stocks"},
        "product_supplied": {"W_EPLLPZ_VPP_NUS_MBBLD": "Product Supplied"},
        "other": {"W_EPLLPZ_VSD_NUS_DAYS": "Days of Supply"},
    },
    "residual": {
        "name": "Residual Fuel Oil",
        "supply": {"WRERPUS2": "Net Production"},
        "disposition": {"WREIMUS2": "Imports", "WREEXUS2": "Exports"},
        "stocks": {"WRESTUS1": "Ending Stocks"},
        "product_supplied": {"WREUPUS2": "Product Supplied"},
        "other": {},
    },
}


def _load_eia_excel():
    """Load and parse EIA weekly petroleum data from the uploaded Excel file."""
    global eia_data_store
    excel_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "PET_SUM_SNDW.xls")
    if not os.path.isfile(excel_path):
        return False
    try:
        xls = pd.ExcelFile(excel_path)
        all_series_data = {}
        for sheet_name in xls.sheet_names:
            if not sheet_name.startswith("Data"):
                continue
            df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
            # Row 0 = title, Row 1 = sourcekeys, Row 2 = descriptions, Row 3+ = data
            sourcekeys = df.iloc[1].tolist()
            descriptions = df.iloc[2].tolist()
            data_df = df.iloc[3:].reset_index(drop=True)
            raw_dates = pd.to_datetime(data_df.iloc[:, 0], errors="coerce")
            valid_mask = raw_dates.notna()
            data_df = data_df[valid_mask].reset_index(drop=True)
            raw_dates = raw_dates[valid_mask].reset_index(drop=True)
            date_strings = raw_dates.dt.strftime("%Y-%m-%d").tolist()
            for col_idx in range(1, len(sourcekeys)):
                sk = sourcekeys[col_idx]
                if pd.isna(sk) or str(sk).strip() == "" or str(sk) == "Sourcekey":
                    continue
                sk = str(sk).strip()
                desc = str(descriptions[col_idx]).strip() if not pd.isna(descriptions[col_idx]) else sk
                col_data = pd.to_numeric(data_df.iloc[:, col_idx], errors="coerce")
                values = [None if pd.isna(v) else round(float(v), 2) for v in col_data.tolist()]
                if date_strings:
                    all_series_data[sk] = {"key": sk, "description": desc, "dates": date_strings, "values": values}
        eia_data_store["series"] = all_series_data
        eia_data_store["loaded"] = True
        print(f"[EIA] Loaded {len(all_series_data)} series from Excel")
        return True
    except Exception as e:
        print(f"[EIA] Failed to load Excel: {e}")
        return False


@app.on_event("startup")
async def load_eia_data():
    """Load EIA data from Excel on startup."""
    if _LEAN_MODE:
        return
    _load_eia_excel()


@app.get("/api/eia/products")
async def eia_list_products():
    """List available EIA products."""
    products = []
    for key, prod in EIA_PRODUCTS.items():
        total_series = sum(len(v) for v in [prod["supply"], prod["disposition"], prod["stocks"], prod["product_supplied"], prod["other"]])
        products.append({"key": key, "name": prod["name"], "series_count": total_series})
    return {"products": products}


@app.get("/api/eia/data/{product}")
async def eia_get_data(product: str, period: str = Query("5Y", description="Time period: 1Y, 2Y, 5Y, 10Y, ALL")):
    """Get EIA supply/demand/stocks data for a product."""
    if product not in EIA_PRODUCTS:
        raise HTTPException(status_code=404, detail=f"Product '{product}' not found")
    if not eia_data_store.get("loaded"):
        _load_eia_excel()
    if not eia_data_store.get("loaded"):
        raise HTTPException(status_code=500, detail="EIA data not loaded")
    prod_def = EIA_PRODUCTS[product]
    series_store = eia_data_store.get("series", {})
    now = pd.Timestamp.now()
    period_map = {"1Y": 365, "2Y": 730, "3Y": 1095, "5Y": 1825, "10Y": 3650, "ALL": 99999}
    days = period_map.get(period, 1825)
    cutoff = (now - pd.Timedelta(days=days)).strftime("%Y-%m-%d")

    def _get_series(series_dict):
        result = {}
        for sk, label in series_dict.items():
            if sk in series_store:
                s = series_store[sk]
                fd, fv = [], []
                for d, v in zip(s["dates"], s["values"]):
                    if d >= cutoff:
                        fd.append(d)
                        fv.append(v)
                result[sk] = {"key": sk, "label": label, "description": s["description"], "dates": fd, "values": fv, "count": len(fd)}
        return result

    supply = _get_series(prod_def["supply"])
    disposition = _get_series(prod_def["disposition"])
    stocks = _get_series(prod_def["stocks"])
    product_supplied = _get_series(prod_def["product_supplied"])
    other = _get_series(prod_def["other"])
    all_series_in_scope = {**supply, **disposition, **stocks, **product_supplied, **other}
    all_dates = set()
    for s in all_series_in_scope.values():
        all_dates.update(s["dates"])
    all_dates = sorted(all_dates)

    # Stock changes
    stock_changes = {}
    for sk, s in stocks.items():
        if len(s["values"]) < 2:
            continue
        changes = [None]
        for i in range(1, len(s["values"])):
            if s["values"][i] is not None and s["values"][i - 1] is not None:
                changes.append(round(s["values"][i] - s["values"][i - 1], 1))
            else:
                changes.append(None)
        stock_changes[sk] = {"key": sk + "_change", "label": s["label"] + " (Weekly Change)", "dates": s["dates"], "values": changes}

    # S&D table (last 52 weeks)
    sd_table = []
    recent_dates = all_dates[-52:] if len(all_dates) > 52 else all_dates
    for d in recent_dates:
        row = {"date": d}
        for sk, s in all_series_in_scope.items():
            try:
                idx = s["dates"].index(d)
                row[sk] = s["values"][idx]
            except ValueError:
                pass
        for sk, sc in stock_changes.items():
            try:
                idx = sc["dates"].index(d)
                row[sc["key"]] = sc["values"][idx]
            except (ValueError, IndexError):
                pass
        sd_table.append(row)

    # Seasonal data for stocks and product supplied
    seasonal = {}
    for sk, s in {**stocks, **product_supplied}.items():
        yearly: dict = {}
        for d, v in zip(s["dates"], s["values"]):
            if v is None:
                continue
            year = d[:4]
            week = pd.Timestamp(d).isocalendar()[1]
            if year not in yearly:
                yearly[year] = {}
            yearly[year][int(week)] = v
        seasonal[sk] = {"label": s["label"], "years": yearly}

    # Also add seasonal for supply series
    for sk, s in supply.items():
        yearly2: dict = {}
        for d, v in zip(s["dates"], s["values"]):
            if v is None:
                continue
            year = d[:4]
            week = pd.Timestamp(d).isocalendar()[1]
            if year not in yearly2:
                yearly2[year] = {}
            yearly2[year][int(week)] = v
        seasonal[sk] = {"label": s["label"], "years": yearly2}

    # 5-year range bands for stocks
    range_bands = {}
    for sk, s in stocks.items():
        weekly_data: dict = {}
        for d, v in zip(s["dates"], s["values"]):
            if v is None:
                continue
            dt = pd.Timestamp(d)
            year = dt.year
            week = int(dt.isocalendar()[1])
            if week not in weekly_data:
                weekly_data[week] = {}
            weekly_data[week][year] = v
        current_year = now.year
        bands = []
        for week in sorted(weekly_data.keys()):
            wd = weekly_data[week]
            hist = {y: v for y, v in wd.items() if current_year - 5 <= y < current_year}
            if hist:
                vals = list(hist.values())
                bands.append({
                    "week": week,
                    "min": round(min(vals), 1),
                    "max": round(max(vals), 1),
                    "avg": round(sum(vals) / len(vals), 1),
                    "current": round(wd[current_year], 1) if current_year in wd else None,
                    "prior_year": round(wd[current_year - 1], 1) if (current_year - 1) in wd else None,
                })
        range_bands[sk] = {"label": s["label"], "bands": bands}

    # Summary stats
    summary = {}
    for sk, s in all_series_in_scope.items():
        non_null = [v for v in s["values"] if v is not None]
        if non_null:
            summary[sk] = {
                "label": s["label"], "latest": non_null[-1], "latest_date": s["dates"][-1] if s["dates"] else None,
                "min": round(min(non_null), 1), "max": round(max(non_null), 1),
                "avg": round(sum(non_null) / len(non_null), 1), "count": len(non_null),
            }

    return {
        "product": product, "product_name": prod_def["name"], "period": period,
        "supply": supply, "disposition": disposition, "stocks": stocks,
        "product_supplied": product_supplied, "other": other,
        "stock_changes": stock_changes, "sd_table": sd_table,
        "seasonal": seasonal, "range_bands": range_bands, "summary": summary,
        "total_dates": len(all_dates),
        "date_range": {"start": all_dates[0] if all_dates else None, "end": all_dates[-1] if all_dates else None},
    }


@app.get("/api/eia/series/{series_key}")
async def eia_get_series(series_key: str):
    """Get raw data for a specific EIA series."""
    if not eia_data_store.get("loaded"):
        _load_eia_excel()
    series_store = eia_data_store.get("series", {})
    if series_key not in series_store:
        raise HTTPException(status_code=404, detail=f"Series '{series_key}' not found")
    s = series_store[series_key]
    return {"key": s["key"], "description": s["description"], "dates": s["dates"], "values": s["values"], "count": len(s["dates"])}


@app.get("/api/eia/compare")
async def eia_compare_series(keys: str = Query(..., description="Comma-separated series keys"), period: str = Query("5Y")):
    """Compare multiple EIA series on the same chart."""
    if not eia_data_store.get("loaded"):
        _load_eia_excel()
    series_store = eia_data_store.get("series", {})
    key_list = [k.strip() for k in keys.split(",")]
    now = pd.Timestamp.now()
    period_map = {"1Y": 365, "2Y": 730, "3Y": 1095, "5Y": 1825, "10Y": 3650, "ALL": 99999}
    days = period_map.get(period, 1825)
    cutoff = (now - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    result = {}
    for k in key_list:
        if k in series_store:
            s = series_store[k]
            fd, fv = [], []
            for d, v in zip(s["dates"], s["values"]):
                if d >= cutoff:
                    fd.append(d)
                    fv.append(v)
            result[k] = {"key": k, "label": s["description"][:60], "dates": fd, "values": fv}
    return {"series": result, "period": period}


# ═══════════════════════════════════════════════════════════════════════════════
# EIA MONTHLY S&D - Supply & Disposition by Area and Product
# ═══════════════════════════════════════════════════════════════════════════════

eia_monthly_store: dict = {"loaded": False, "areas": {}}

EIA_MONTHLY_AREAS = {
    "nus": "U.S.",
    "r10": "PADD 1",
    "r20": "PADD 2",
    "r30": "PADD 3",
    "r40": "PADD 4",
    "r50": "PADD 5",
}

# Component classification keywords
_SUPPLY_KEYWORDS = ["Field Production", "Gas Plant Production", "Transfers to Crude Oil Supply",
                     "Biofuels Plant Net Production", "Refinery and Blender Net Production",
                     "Renewable Fuels", "Imports", "Net Receipts"]
_DISPOSITION_KEYWORDS = ["Stock Change", "Refinery and Blender Net Input", "Exports",
                         "Product Supplied", "Supply Adjustment"]
_STOCK_KEYWORDS = ["Ending Stocks"]


def _classify_component(desc: str) -> str:
    """Classify a series description as supply, disposition, stock_change, or other."""
    desc_up = desc.upper()
    if "ENDING STOCKS" in desc_up:
        return "ending_stocks"
    if "STOCK CHANGE" in desc_up:
        return "stock_change"
    if "PRODUCT SUPPLIED" in desc_up:
        return "product_supplied"
    if "EXPORTS" in desc_up:
        return "exports"
    if "SUPPLY ADJUSTMENT" in desc_up or "ADJUSTMENTS" in desc_up:
        return "adjustments"
    if "REFINERY AND BLENDER NET INPUT" in desc_up:
        return "refinery_input"
    if "NET RECEIPTS" in desc_up:
        return "net_receipts"
    if "IMPORTS" in desc_up:
        return "imports"
    if "FIELD PRODUCTION" in desc_up or "GAS PLANT PRODUCTION" in desc_up:
        return "field_production"
    if "TRANSFERS TO CRUDE OIL SUPPLY" in desc_up:
        return "transfers"
    if "BIOFUELS PLANT" in desc_up or "RENEWABLE FUELS" in desc_up:
        return "biofuels_production"
    if "REFINERY AND BLENDER NET PRODUCTION" in desc_up:
        return "refinery_production"
    return "other"


def _get_component_category(comp_type: str) -> str:
    """Map component type to supply or disposition."""
    supply_types = {"field_production", "transfers", "biofuels_production",
                    "refinery_production", "imports", "net_receipts"}
    disposition_types = {"stock_change", "refinery_input", "exports",
                         "product_supplied", "adjustments"}
    if comp_type in supply_types:
        return "supply"
    if comp_type in disposition_types:
        return "disposition"
    if comp_type == "ending_stocks":
        return "ending_stocks"
    return "other"


def _extract_product_name(desc: str, area_name: str) -> str:
    """Extract product name from EIA description string."""
    import re
    # Remove the area prefix (e.g., "U.S.", "PADD 1")
    d = desc.replace(area_name, "").strip()
    # Remove the unit suffix
    d = re.sub(r'\s*\(Thousand Barrels.*$', '', d)
    # Remove component words to get product
    for kw in ["Field Production of", "Gas Plant Production of",
               "Transfers to Crude Oil Supply of",
               "Biofuels Plant Net Production of",
               "Renewable Fuels and Oxygenate Plant Net Production of",
               "Refinery and Blender Net Production of",
               "Refinery and Blender Net Input of",
               "Imports of", "Exports of", "Net Receipts of",
               "Supply Adjustment of", "Product Supplied of",
               "Stock Change", "Ending Stocks of",
               "Finished Petroleum Products"]:
        d = d.replace(kw, "").strip()
    # Clean up
    d = re.sub(r'^[\s,\-]+', '', d).strip()
    d = re.sub(r'[\s,\-]+$', '', d).strip()
    if not d or len(d) < 3:
        return "Total Petroleum"
    return d


def _load_eia_monthly():
    """Load and parse all EIA monthly S&D Excel files."""
    global eia_monthly_store
    import re
    eia_dir = "/home/ubuntu/eia_data"
    if not os.path.isdir(eia_dir):
        print("[EIA-Monthly] Data directory not found")
        return False
    areas_data = {}
    for area_code, area_name in EIA_MONTHLY_AREAS.items():
        fpath = os.path.join(eia_dir, f"{area_code}_monthly.xls")
        if not os.path.isfile(fpath):
            print(f"[EIA-Monthly] File not found: {fpath}")
            continue
        try:
            xls = pd.ExcelFile(fpath)
            area_products: dict = {}
            for sheet_name in xls.sheet_names:
                if not sheet_name.startswith("Data"):
                    continue
                df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
                if len(df) < 4:
                    continue
                sheet_title = str(df.iloc[0, 1]) if not pd.isna(df.iloc[0, 1]) else sheet_name
                skeys = df.iloc[1].tolist()
                descs = df.iloc[2].tolist()
                # Parse dates
                data_df = df.iloc[3:].reset_index(drop=True)
                raw_dates = pd.to_datetime(data_df.iloc[:, 0], errors="coerce")
                valid_mask = raw_dates.notna()
                data_df = data_df[valid_mask].reset_index(drop=True)
                raw_dates = raw_dates[valid_mask].reset_index(drop=True)
                date_strings = raw_dates.dt.strftime("%Y-%m").tolist()
                if not date_strings:
                    continue
                for col_idx in range(1, len(skeys)):
                    sk = skeys[col_idx]
                    if pd.isna(sk) or str(sk).strip() in ("", "Sourcekey"):
                        continue
                    sk = str(sk).strip()
                    desc = str(descs[col_idx]).strip() if not pd.isna(descs[col_idx]) else sk
                    # Parse values
                    col_data = pd.to_numeric(data_df.iloc[:, col_idx], errors="coerce")
                    values = [None if pd.isna(v) else round(float(v), 1) for v in col_data.tolist()]
                    # Classify component
                    comp_type = _classify_component(desc)
                    category = _get_component_category(comp_type)
                    # Extract product name
                    product_name = _extract_product_name(desc, area_name)
                    # Clean the component label from the description
                    label = desc
                    # Remove area prefix and unit for shorter label
                    label = re.sub(rf'^{re.escape(area_name)}\s+', '', label)
                    label = re.sub(r'\s*\(Thousand Barrels.*$', '', label)
                    if product_name not in area_products:
                        area_products[product_name] = {"supply": {}, "disposition": {}, "ending_stocks": {}, "other": {}}
                    area_products[product_name][category][sk] = {
                        "key": sk, "label": label, "description": desc,
                        "comp_type": comp_type,
                        "dates": date_strings, "values": values,
                    }
            areas_data[area_code] = {
                "name": area_name,
                "products": area_products,
                "product_count": len(area_products),
            }
            print(f"[EIA-Monthly] Loaded {area_name}: {len(area_products)} products")
        except Exception as e:
            print(f"[EIA-Monthly] Error loading {area_name}: {e}")
    eia_monthly_store["areas"] = areas_data
    eia_monthly_store["loaded"] = True
    print(f"[EIA-Monthly] Loaded {len(areas_data)} areas total")
    return True


@app.on_event("startup")
async def load_eia_monthly_data():
    if _LEAN_MODE:
        return
    _load_eia_monthly()


@app.get("/api/eia_sd/areas")
async def eia_sd_list_areas():
    """List available areas with product counts."""
    if not eia_monthly_store.get("loaded"):
        _load_eia_monthly()
    areas = []
    for code, info in eia_monthly_store.get("areas", {}).items():
        areas.append({"code": code, "name": info["name"], "product_count": info["product_count"]})
    return {"areas": areas}


@app.get("/api/eia_sd/products")
async def eia_sd_list_products(area: str = Query("nus")):
    """List available products for a given area."""
    if not eia_monthly_store.get("loaded"):
        _load_eia_monthly()
    area_data = eia_monthly_store.get("areas", {}).get(area)
    if not area_data:
        raise HTTPException(status_code=404, detail=f"Area '{area}' not found")
    products = []
    for pname, pdata in area_data["products"].items():
        total = sum(len(v) for v in [pdata["supply"], pdata["disposition"], pdata["ending_stocks"], pdata["other"]])
        products.append({"name": pname, "series_count": total,
                         "supply_count": len(pdata["supply"]),
                         "disposition_count": len(pdata["disposition"])})
    # Sort: main products first
    priority = ["Crude Oil", "Total Petroleum", "Finished Motor Gasoline",
                "Motor Gasoline", "Distillate Fuel Oil", "Kerosene-Type Jet Fuel",
                "Residual Fuel Oil", "Propane", "Hydrocarbon Gas Liquids"]
    def sort_key(p):
        name = p["name"]
        for i, pr in enumerate(priority):
            if pr.lower() in name.lower():
                return (i, name)
        return (100, name)
    products.sort(key=sort_key)
    return {"area": area, "area_name": area_data["name"], "products": products}


@app.get("/api/eia_sd/data")
async def eia_sd_get_data(area: str = Query("nus"), product: str = Query("Crude Oil"),
                          period: str = Query("10Y")):
    """Get full S&D data for a product in an area."""
    if not eia_monthly_store.get("loaded"):
        _load_eia_monthly()
    area_data = eia_monthly_store.get("areas", {}).get(area)
    if not area_data:
        raise HTTPException(status_code=404, detail=f"Area '{area}' not found")
    # Find product (case-insensitive partial match)
    pdata = None
    pname_found = None
    for pname, pd_item in area_data["products"].items():
        if pname.lower() == product.lower() or product.lower() in pname.lower():
            pdata = pd_item
            pname_found = pname
            break
    if not pdata:
        raise HTTPException(status_code=404, detail=f"Product '{product}' not found in {area_data['name']}")
    # Apply period filter
    now = pd.Timestamp.now()
    period_map = {"1Y": 365, "2Y": 730, "5Y": 1825, "10Y": 3650, "20Y": 7300, "ALL": 99999}
    days = period_map.get(period, 3650)
    cutoff = (now - pd.Timedelta(days=days)).strftime("%Y-%m")

    def _filter_series(series_dict):
        result = {}
        for sk, s in series_dict.items():
            fd, fv = [], []
            for d, v in zip(s["dates"], s["values"]):
                if d >= cutoff:
                    fd.append(d)
                    fv.append(v)
            result[sk] = {"key": sk, "label": s["label"], "description": s["description"],
                          "comp_type": s["comp_type"],
                          "dates": fd, "values": fv, "count": len(fd)}
        return result

    supply = _filter_series(pdata["supply"])
    disposition = _filter_series(pdata["disposition"])
    ending_stocks = _filter_series(pdata["ending_stocks"])
    other = _filter_series(pdata["other"])
    # Collect all dates
    all_dates = set()
    for cat in [supply, disposition, ending_stocks, other]:
        for s in cat.values():
            all_dates.update(s["dates"])
    all_dates = sorted(all_dates)
    # Build S&D table
    sd_table = []
    for d in all_dates:
        row: dict = {"date": d}
        for cat_name, cat_data in [("supply", supply), ("disposition", disposition),
                                   ("ending_stocks", ending_stocks), ("other", other)]:
            for sk, s in cat_data.items():
                try:
                    idx = s["dates"].index(d)
                    row[sk] = s["values"][idx]
                except (ValueError, IndexError):
                    pass
        sd_table.append(row)
    # Compute total supply and total disposition per date
    supply_total = []
    disposition_total = []
    stock_change_series = []
    for d in all_dates:
        s_val = 0.0
        d_val = 0.0
        s_count = 0
        d_count = 0
        for sk, s in supply.items():
            try:
                idx = s["dates"].index(d)
                v = s["values"][idx]
                if v is not None:
                    s_val += v
                    s_count += 1
            except (ValueError, IndexError):
                pass
        for sk, s in disposition.items():
            if s["comp_type"] == "stock_change":
                continue  # Don't include stock change in disposition total
            try:
                idx = s["dates"].index(d)
                v = s["values"][idx]
                if v is not None:
                    d_val += v
                    d_count += 1
            except (ValueError, IndexError):
                pass
        supply_total.append(round(s_val, 1) if s_count > 0 else None)
        disposition_total.append(round(d_val, 1) if d_count > 0 else None)
        # Stock change = supply - disposition
        if s_count > 0 and d_count > 0:
            stock_change_series.append(round(s_val - d_val, 1))
        else:
            stock_change_series.append(None)
    # Seasonal for key series
    seasonal = {}
    for cat in [supply, disposition, ending_stocks]:
        for sk, s in cat.items():
            yearly: dict = {}
            for d, v in zip(s["dates"], s["values"]):
                if v is None:
                    continue
                year = d[:4]
                month = int(d[5:7])
                if year not in yearly:
                    yearly[year] = {}
                yearly[year][month] = v
            if yearly:
                seasonal[sk] = {"label": s["label"], "years": yearly}
    # Summary stats
    summary = {}
    for cat in [supply, disposition, ending_stocks, other]:
        for sk, s in cat.items():
            non_null = [v for v in s["values"] if v is not None]
            if non_null:
                summary[sk] = {
                    "label": s["label"], "comp_type": s["comp_type"],
                    "latest": non_null[-1],
                    "latest_date": s["dates"][-1] if s["dates"] else None,
                    "min": round(min(non_null), 1),
                    "max": round(max(non_null), 1),
                    "avg": round(sum(non_null) / len(non_null), 1),
                    "count": len(non_null),
                }
    return {
        "area": area, "area_name": area_data["name"],
        "product": pname_found, "period": period,
        "supply": supply, "disposition": disposition,
        "ending_stocks": ending_stocks, "other": other,
        "sd_table": sd_table,
        "all_dates": all_dates,
        "supply_total": {"dates": all_dates, "values": supply_total},
        "disposition_total": {"dates": all_dates, "values": disposition_total},
        "stock_change_calc": {"dates": all_dates, "values": stock_change_series,
                              "label": "Implied Stock Change (Supply - Disposition)"},
        "seasonal": seasonal,
        "summary": summary,
        "date_range": {"start": all_dates[0] if all_dates else None,
                       "end": all_dates[-1] if all_dates else None},
        "total_months": len(all_dates),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EIA S&D FORECAST & CORRELATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _forecast_series(dates: list, values: list, months_ahead: int = 12) -> dict:
    """Generate forecasts for a single series using multiple methods."""
    import math
    # Clean data
    clean_pairs = [(d, v) for d, v in zip(dates, values) if v is not None]
    if len(clean_pairs) < 12:
        return {"dates": [], "methods": {}}
    cd, cv = zip(*clean_pairs)
    cv_arr = np.array(cv, dtype=float)
    n = len(cv_arr)
    # Last date
    last_date_str = cd[-1]
    last_year = int(last_date_str[:4])
    last_month = int(last_date_str[5:7])
    # Generate future dates
    future_dates = []
    y, m = last_year, last_month
    for _ in range(months_ahead):
        m += 1
        if m > 12:
            m = 1
            y += 1
        future_dates.append(f"{y:04d}-{m:02d}")

    methods = {}

    # Method 1: 3-Month Moving Average
    ma3 = float(np.mean(cv_arr[-3:]))
    methods["3m_avg"] = {"label": "3-Month Average", "values": [round(ma3, 1)] * months_ahead}

    # Method 2: 12-Month Moving Average
    ma12 = float(np.mean(cv_arr[-12:]))
    methods["12m_avg"] = {"label": "12-Month Average", "values": [round(ma12, 1)] * months_ahead}

    # Method 3: Seasonal (same month from last year, or avg of last 3 same-months)
    seasonal_vals = []
    for fd in future_dates:
        fm = int(fd[5:7])
        same_month_vals = []
        for dd, vv in zip(cd, cv):
            if int(dd[5:7]) == fm:
                same_month_vals.append(vv)
        if len(same_month_vals) >= 3:
            seasonal_vals.append(round(float(np.mean(same_month_vals[-3:])), 1))
        elif same_month_vals:
            seasonal_vals.append(round(float(same_month_vals[-1]), 1))
        else:
            seasonal_vals.append(round(ma12, 1))
    methods["seasonal"] = {"label": "Seasonal (3yr avg)", "values": seasonal_vals}

    # Method 4: Linear Trend
    x = np.arange(n, dtype=float)
    try:
        coeffs = np.polyfit(x, cv_arr, 1)
        trend_vals = []
        for i in range(months_ahead):
            pred = coeffs[0] * (n + i) + coeffs[1]
            trend_vals.append(round(float(pred), 1))
        methods["linear_trend"] = {"label": "Linear Trend", "values": trend_vals}
    except Exception:
        methods["linear_trend"] = {"label": "Linear Trend", "values": [round(ma12, 1)] * months_ahead}

    # Method 5: Seasonal + Trend (hybrid)
    # Use last year's seasonal pattern + apply recent trend
    if n >= 24:
        recent_trend = float(np.mean(np.diff(cv_arr[-12:])))
        hybrid_vals = []
        for i, fd in enumerate(future_dates):
            fm = int(fd[5:7])
            same_month = [vv for dd, vv in zip(cd, cv) if int(dd[5:7]) == fm]
            if len(same_month) >= 2:
                base = float(same_month[-1])
                hybrid_vals.append(round(base + recent_trend * (i + 1), 1))
            else:
                hybrid_vals.append(round(ma12 + recent_trend * (i + 1), 1))
        methods["seasonal_trend"] = {"label": "Seasonal + Trend", "values": hybrid_vals}
    else:
        methods["seasonal_trend"] = {"label": "Seasonal + Trend", "values": seasonal_vals}

    # Method 6: AI Ensemble (weighted average of all methods)
    ensemble_vals = []
    weights = {"seasonal": 0.35, "seasonal_trend": 0.25, "linear_trend": 0.15, "3m_avg": 0.15, "12m_avg": 0.10}
    for i in range(months_ahead):
        wsum = 0.0
        wtotal = 0.0
        for mk, w in weights.items():
            if mk in methods and i < len(methods[mk]["values"]):
                wsum += methods[mk]["values"][i] * w
                wtotal += w
        if wtotal > 0:
            ensemble_vals.append(round(wsum / wtotal, 1))
        else:
            ensemble_vals.append(round(ma12, 1))
    methods["ai_ensemble"] = {"label": "AI Ensemble", "values": ensemble_vals}

    return {"dates": future_dates, "methods": methods,
            "last_actual_date": last_date_str, "last_actual_value": round(float(cv_arr[-1]), 1)}


@app.get("/api/eia_sd/forecast")
async def eia_sd_forecast(area: str = Query("nus"), product: str = Query("Crude Oil"),
                          months: int = Query(12)):
    """Generate S&D forecasts for all components of a product."""
    if not eia_monthly_store.get("loaded"):
        _load_eia_monthly()
    area_data = eia_monthly_store.get("areas", {}).get(area)
    if not area_data:
        raise HTTPException(status_code=404, detail=f"Area '{area}' not found")
    pdata = None
    pname_found = None
    for pname, pd_item in area_data["products"].items():
        if pname.lower() == product.lower() or product.lower() in pname.lower():
            pdata = pd_item
            pname_found = pname
            break
    if not pdata:
        raise HTTPException(status_code=404, detail=f"Product '{product}' not found")
    months = min(max(months, 1), 36)

    forecasts = {}
    for cat_name, cat_data in [("supply", pdata["supply"]), ("disposition", pdata["disposition"]),
                                ("ending_stocks", pdata["ending_stocks"])]:
        for sk, s in cat_data.items():
            fc = _forecast_series(s["dates"], s["values"], months)
            if fc["dates"]:
                forecasts[sk] = {
                    "label": s["label"], "comp_type": s["comp_type"], "category": cat_name,
                    "forecast": fc
                }

    # Build forecast balance sheet: for each future month, show all components
    future_dates = []
    if forecasts:
        first_fc = next(iter(forecasts.values()))
        future_dates = first_fc["forecast"]["dates"]

    balance_sheet = []
    for i, fd in enumerate(future_dates):
        row = {"date": fd, "is_forecast": True}
        supply_total = 0.0
        disp_total = 0.0
        s_count = 0
        d_count = 0
        for sk, fc_info in forecasts.items():
            # Use AI ensemble by default
            vals = fc_info["forecast"]["methods"].get("ai_ensemble", {}).get("values", [])
            if i < len(vals):
                row[sk] = vals[i]
                if fc_info["category"] == "supply":
                    supply_total += vals[i]
                    s_count += 1
                elif fc_info["category"] == "disposition" and fc_info["comp_type"] != "stock_change":
                    disp_total += vals[i]
                    d_count += 1
        row["supply_total"] = round(supply_total, 1) if s_count > 0 else None
        row["disposition_total"] = round(disp_total, 1) if d_count > 0 else None
        row["implied_stock_change"] = round(supply_total - disp_total, 1) if s_count > 0 and d_count > 0 else None
        balance_sheet.append(row)

    # Also include last 6 actual months for context
    actual_rows = []
    all_series = {**pdata["supply"], **pdata["disposition"], **pdata["ending_stocks"]}
    # Get last 6 dates
    all_actual_dates = set()
    for s in all_series.values():
        all_actual_dates.update(s["dates"][-6:])
    for d in sorted(all_actual_dates)[-6:]:
        row = {"date": d, "is_forecast": False}
        supply_total = 0.0
        disp_total = 0.0
        s_count = 0
        d_count = 0
        for sk, s in all_series.items():
            try:
                idx = s["dates"].index(d)
                v = s["values"][idx]
                if v is not None:
                    row[sk] = v
                    cat = _get_component_category(s["comp_type"])
                    if cat == "supply":
                        supply_total += v
                        s_count += 1
                    elif cat == "disposition" and s["comp_type"] != "stock_change":
                        disp_total += v
                        d_count += 1
            except (ValueError, IndexError):
                pass
        row["supply_total"] = round(supply_total, 1) if s_count > 0 else None
        row["disposition_total"] = round(disp_total, 1) if d_count > 0 else None
        row["implied_stock_change"] = round(supply_total - disp_total, 1) if s_count > 0 and d_count > 0 else None
        actual_rows.append(row)

    return {
        "area": area, "area_name": area_data["name"],
        "product": pname_found,
        "months_ahead": months,
        "forecasts": forecasts,
        "balance_sheet": actual_rows + balance_sheet,
        "future_dates": future_dates,
        "series_keys": list(forecasts.keys()),
    }


@app.post("/api/eia_sd/adjust_forecast")
async def eia_sd_adjust_forecast(body: dict):
    """Recalculate balance sheet with user-adjusted forecast values.
    body: { adjustments: { series_key: { date: value, ... }, ... },
            area, product, months, method }
    """
    area = body.get("area", "nus")
    product = body.get("product", "Crude Oil")
    months = body.get("months", 12)
    method = body.get("method", "ai_ensemble")
    adjustments = body.get("adjustments", {})

    if not eia_monthly_store.get("loaded"):
        _load_eia_monthly()
    area_data = eia_monthly_store.get("areas", {}).get(area)
    if not area_data:
        raise HTTPException(status_code=404, detail=f"Area '{area}' not found")
    pdata = None
    pname_found = None
    for pname, pd_item in area_data["products"].items():
        if pname.lower() == product.lower() or product.lower() in pname.lower():
            pdata = pd_item
            pname_found = pname
            break
    if not pdata:
        raise HTTPException(status_code=404, detail=f"Product '{product}' not found")

    months = min(max(months, 1), 36)
    forecasts = {}
    for cat_name, cat_data in [("supply", pdata["supply"]), ("disposition", pdata["disposition"]),
                                ("ending_stocks", pdata["ending_stocks"])]:
        for sk, s in cat_data.items():
            fc = _forecast_series(s["dates"], s["values"], months)
            if fc["dates"]:
                forecasts[sk] = {
                    "label": s["label"], "comp_type": s["comp_type"], "category": cat_name,
                    "forecast": fc
                }

    future_dates = []
    if forecasts:
        first_fc = next(iter(forecasts.values()))
        future_dates = first_fc["forecast"]["dates"]

    balance_sheet = []
    for i, fd in enumerate(future_dates):
        row = {"date": fd, "is_forecast": True}
        supply_total = 0.0
        disp_total = 0.0
        s_count = 0
        d_count = 0
        for sk, fc_info in forecasts.items():
            # Check if user adjusted this value
            if sk in adjustments and fd in adjustments[sk]:
                val = float(adjustments[sk][fd])
            else:
                vals = fc_info["forecast"]["methods"].get(method, fc_info["forecast"]["methods"].get("ai_ensemble", {})).get("values", [])
                val = vals[i] if i < len(vals) else 0
            row[sk] = round(val, 1)
            if fc_info["category"] == "supply":
                supply_total += val
                s_count += 1
            elif fc_info["category"] == "disposition" and fc_info["comp_type"] != "stock_change":
                disp_total += val
                d_count += 1
        row["supply_total"] = round(supply_total, 1) if s_count > 0 else None
        row["disposition_total"] = round(disp_total, 1) if d_count > 0 else None
        row["implied_stock_change"] = round(supply_total - disp_total, 1) if s_count > 0 and d_count > 0 else None
        balance_sheet.append(row)

    return {
        "area": area, "area_name": area_data["name"],
        "product": pname_found,
        "method": method,
        "balance_sheet": balance_sheet,
        "future_dates": future_dates,
        "series_keys": list(forecasts.keys()),
    }


@app.get("/api/eia_sd/correlations")
async def eia_sd_correlations(area: str = Query("nus"), product: str = Query("Crude Oil")):
    """Compute major correlations between S&D components."""
    if not eia_monthly_store.get("loaded"):
        _load_eia_monthly()
    area_data = eia_monthly_store.get("areas", {}).get(area)
    if not area_data:
        raise HTTPException(status_code=404, detail=f"Area '{area}' not found")
    pdata = None
    pname_found = None
    for pname, pd_item in area_data["products"].items():
        if pname.lower() == product.lower() or product.lower() in pname.lower():
            pdata = pd_item
            pname_found = pname
            break
    if not pdata:
        raise HTTPException(status_code=404, detail=f"Product '{product}' not found")

    # Collect all series into a date-aligned DataFrame
    all_series = {}
    for cat_name, cat_data in [("supply", pdata["supply"]), ("disposition", pdata["disposition"]),
                                ("ending_stocks", pdata["ending_stocks"]), ("other", pdata["other"])]:
        for sk, s in cat_data.items():
            all_series[sk] = s

    # Build aligned data
    all_dates_set = set()
    for s in all_series.values():
        all_dates_set.update(s["dates"])
    all_dates = sorted(all_dates_set)

    df_data = {"date": all_dates}
    labels = {}
    comp_types = {}
    for sk, s in all_series.items():
        col_vals = []
        for d in all_dates:
            try:
                idx = s["dates"].index(d)
                col_vals.append(s["values"][idx])
            except (ValueError, IndexError):
                col_vals.append(None)
        df_data[sk] = col_vals
        labels[sk] = s["label"]
        comp_types[sk] = s["comp_type"]

    df = pd.DataFrame(df_data)
    df.set_index("date", inplace=True)

    # Compute correlation matrix
    numeric_cols = [c for c in df.columns if df[c].notna().sum() > 12]
    if len(numeric_cols) < 2:
        return {"area": area, "product": pname_found, "pairs": [], "matrix": {}}

    corr_matrix = df[numeric_cols].corr().round(3)

    # Find interesting correlation pairs
    pairs = []
    seen = set()
    for i, c1 in enumerate(numeric_cols):
        for j, c2 in enumerate(numeric_cols):
            if i >= j:
                continue
            key = tuple(sorted([c1, c2]))
            if key in seen:
                continue
            seen.add(key)
            r = corr_matrix.loc[c1, c2]
            if pd.isna(r):
                continue
            pairs.append({
                "series1_key": c1, "series1_label": labels.get(c1, c1),
                "series1_type": comp_types.get(c1, ""),
                "series2_key": c2, "series2_label": labels.get(c2, c2),
                "series2_type": comp_types.get(c2, ""),
                "correlation": float(r),
                "abs_correlation": abs(float(r)),
            })

    # Sort by absolute correlation (most interesting first)
    pairs.sort(key=lambda x: x["abs_correlation"], reverse=True)

    # Pre-select important pairs for display
    important_pairs = []
    # Define pairs traders care about
    desired = [
        ("imports", "refinery_input"),
        ("field_production", "exports"),
        ("refinery_production", "product_supplied"),
        ("imports", "exports"),
        ("field_production", "refinery_input"),
        ("refinery_input", "refinery_production"),
        ("imports", "ending_stocks"),
        ("field_production", "ending_stocks"),
        ("product_supplied", "ending_stocks"),
        ("exports", "ending_stocks"),
    ]
    for t1, t2 in desired:
        for p in pairs:
            if ((p["series1_type"] == t1 and p["series2_type"] == t2) or
                (p["series1_type"] == t2 and p["series2_type"] == t1)):
                if p not in important_pairs:
                    important_pairs.append(p)
                break
    # Add top correlated pairs not already included
    for p in pairs[:20]:
        if p not in important_pairs:
            important_pairs.append(p)

    # Build scatter data for top pairs
    scatter_data = {}
    for p in important_pairs[:12]:
        k1, k2 = p["series1_key"], p["series2_key"]
        s1 = df[k1].dropna()
        s2 = df[k2].dropna()
        common = s1.index.intersection(s2.index)
        if len(common) < 10:
            continue
        points = [{"x": round(float(s1[d]), 1), "y": round(float(s2[d]), 1), "date": d}
                  for d in common[-120:]]
        scatter_data[f"{k1}__{k2}"] = {
            "series1_label": p["series1_label"],
            "series2_label": p["series2_label"],
            "correlation": p["correlation"],
            "points": points,
        }

    # Rolling correlations for important pairs (12-month window)
    rolling_data = {}
    for p in important_pairs[:8]:
        k1, k2 = p["series1_key"], p["series2_key"]
        s1 = df[k1]
        s2 = df[k2]
        common_idx = s1.dropna().index.intersection(s2.dropna().index)
        if len(common_idx) < 24:
            continue
        s1_aligned = s1.loc[common_idx]
        s2_aligned = s2.loc[common_idx]
        rolling_corr = s1_aligned.rolling(12, min_periods=6).corr(s2_aligned)
        rc_clean = rolling_corr.dropna()
        rolling_data[f"{k1}__{k2}"] = {
            "series1_label": p["series1_label"],
            "series2_label": p["series2_label"],
            "dates": rc_clean.index.tolist(),
            "values": [round(float(v), 3) for v in rc_clean.values],
        }

    return {
        "area": area, "area_name": area_data["name"],
        "product": pname_found,
        "pairs": important_pairs,
        "scatter_data": scatter_data,
        "rolling_correlations": rolling_data,
        "matrix": {c: {c2: float(corr_matrix.loc[c, c2]) if not pd.isna(corr_matrix.loc[c, c2]) else None
                        for c2 in numeric_cols}
                   for c in numeric_cols},
        "series_labels": labels,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# CRUDE BALANCES (Sweet / Sour / Total by Region)
# ═══════════════════════════════════════════════════════════════════════════════

cb_store: dict = {}

def _load_crude_balances():
    """Parse Crude Balances Excel file (Sweet/Sour/Total by region/month)."""
    import math
    fpath = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "balnacestoupload.xlsx")
    if not os.path.exists(fpath):
        return
    wb = openpyxl.load_workbook(fpath, data_only=True)
    ws = wb[wb.sheetnames[0]]

    sections = {}
    for start_row, section_name in [(3, "sweet"), (11, "sour"), (19, "total")]:
        dates = []
        for c in range(2, ws.max_column + 1):
            v = ws.cell(start_row, c).value
            if v is None:
                continue
            if hasattr(v, "strftime"):
                dates.append(v.strftime("%Y-%m"))
            else:
                dates.append(str(v)[:7])
        regions = {}
        for offset in range(1, 7):
            r = start_row + offset
            region_name = ws.cell(r, 1).value
            if region_name is None:
                continue
            region_name = str(region_name).strip()
            values = []
            for c in range(2, 2 + len(dates)):
                v = ws.cell(r, c).value
                if v is None or v == "":
                    values.append(None)
                else:
                    try:
                        values.append(float(v))
                    except (ValueError, TypeError):
                        values.append(None)
            regions[region_name] = values
        sections[section_name] = {"dates": dates, "regions": regions}

    cb_store["sections"] = sections
    cb_store["loaded"] = True
    region_names = list(sections["sweet"]["regions"].keys())
    n_dates = len(sections["sweet"]["dates"])
    print(f"[CB] Loaded balances: {len(region_names)} regions, {n_dates} months")
    print(f"[CB] Regions: {region_names}")


def _ensure_cb():
    if not cb_store.get("loaded"):
        _load_crude_balances()
    if not cb_store.get("loaded"):
        raise HTTPException(status_code=404, detail="Crude Balances data not loaded")
    return cb_store["sections"]


@app.on_event("startup")
async def load_cb_data():
    if _LEAN_MODE:
        return
    try:
        _load_crude_balances()
    except Exception as e:
        print(f"[CB] Failed to load: {e}")


@app.get("/api/cb/overview")
async def cb_overview():
    secs = _ensure_cb()
    cards = []
    by_type = {}
    dates = secs["sweet"]["dates"]
    for btype in ["sweet", "sour", "total"]:
        sec = secs[btype]
        by_type[btype] = {}
        for region, vals in sec["regions"].items():
            by_type[btype][region] = vals
            valid = [v for v in vals if v is not None]
            latest = valid[-1] if valid else None
            prev = valid[-2] if len(valid) >= 2 else None
            avg_12m = sum(valid[-12:]) / len(valid[-12:]) if len(valid) >= 12 else (sum(valid) / len(valid) if valid else None)
            cards.append({
                "region": region,
                "balance_type": btype.upper(),
                "latest": latest,
                "change": round(latest - prev, 2) if latest is not None and prev is not None else None,
                "avg_12m": round(avg_12m, 2) if avg_12m is not None else None,
                "cum_sum": round(sum(valid), 2) if valid else None,
            })
    return {"cards": cards, "by_type": by_type, "dates": dates}


@app.get("/api/cb/chart")
async def cb_chart(balance_type: str = Query("total"), region: str = Query("GLOBAL")):
    secs = _ensure_cb()
    if balance_type not in secs:
        raise HTTPException(400, f"Invalid balance_type: {balance_type}")
    sec = secs[balance_type]
    dates = sec["dates"]
    vals = sec["regions"].get(region)
    if vals is None:
        raise HTTPException(400, f"Invalid region: {region}")
    cumulative = []
    cum = 0
    for v in vals:
        if v is not None:
            cum += v
        cumulative.append(round(cum, 2))
    valid = [v for v in vals if v is not None]
    import statistics
    stats = {
        "latest": valid[-1] if valid else None,
        "mean": round(statistics.mean(valid), 2) if valid else None,
        "std": round(statistics.stdev(valid), 2) if len(valid) > 1 else None,
        "min": min(valid) if valid else None,
        "max": max(valid) if valid else None,
    }
    return {"balance_type": balance_type, "region": region, "dates": dates, "values": vals, "cumulative": cumulative, "stats": stats}


@app.get("/api/cb/compare_regions")
async def cb_compare_regions(balance_type: str = Query("total")):
    secs = _ensure_cb()
    if balance_type not in secs:
        raise HTTPException(400, f"Invalid balance_type: {balance_type}")
    sec = secs[balance_type]
    dates = sec["dates"]
    regions = list(sec["regions"].keys())
    series = {r: sec["regions"][r] for r in regions}
    latest = {}
    for r in regions:
        valid = [v for v in sec["regions"][r] if v is not None]
        latest[r] = valid[-1] if valid else None
    return {"balance_type": balance_type, "regions": regions, "dates": dates, "series": series, "latest": latest}


@app.get("/api/cb/compare_types")
async def cb_compare_types(region: str = Query("GLOBAL")):
    secs = _ensure_cb()
    dates = secs["sweet"]["dates"]
    types = ["sweet", "sour", "total"]
    series = {}
    for btype in types:
        vals = secs[btype]["regions"].get(region)
        series[btype] = vals if vals else [None] * len(dates)
    return {"region": region, "types": types, "dates": dates, "series": series}


@app.get("/api/cb/cumulative")
async def cb_cumulative(balance_type: str = Query("total")):
    secs = _ensure_cb()
    if balance_type not in secs:
        raise HTTPException(400, f"Invalid balance_type: {balance_type}")
    sec = secs[balance_type]
    dates = sec["dates"]
    regions = list(sec["regions"].keys())
    cumulative = {}
    for reg in regions:
        cum = 0
        cum_vals = []
        for v in sec["regions"][reg]:
            if v is not None:
                cum += v
            cum_vals.append(round(cum, 2))
        cumulative[reg] = cum_vals
    return {"balance_type": balance_type, "regions": regions, "dates": dates, "cumulative": cumulative}


@app.get("/api/cb/seasonal")
async def cb_seasonal(balance_type: str = Query("total"), region: str = Query("GLOBAL")):
    import statistics
    secs = _ensure_cb()
    if balance_type not in secs:
        raise HTTPException(400, f"Invalid balance_type: {balance_type}")
    vals = secs[balance_type]["regions"].get(region)
    dates = secs[balance_type]["dates"]
    if vals is None:
        raise HTTPException(400, f"Invalid region: {region}")
    yearly = {}
    for i, d in enumerate(dates):
        yr = d[:4]
        mo = int(d[5:7])
        if yr not in yearly:
            yearly[yr] = [None] * 12
        yearly[yr][mo - 1] = vals[i]
    years = sorted(yearly.keys())
    avg = []
    range_min = []
    range_max = []
    monthly_stats = {"avg": [], "min": [], "max": [], "std": []}
    for mi in range(12):
        month_vals = [yearly[yr][mi] for yr in years if yearly[yr][mi] is not None]
        if month_vals:
            avg.append(round(sum(month_vals) / len(month_vals), 2))
            range_min.append(min(month_vals))
            range_max.append(max(month_vals))
            monthly_stats["avg"].append(round(sum(month_vals) / len(month_vals), 2))
            monthly_stats["min"].append(min(month_vals))
            monthly_stats["max"].append(max(month_vals))
            monthly_stats["std"].append(round(statistics.stdev(month_vals), 2) if len(month_vals) > 1 else 0)
        else:
            avg.append(None)
            range_min.append(None)
            range_max.append(None)
            monthly_stats["avg"].append(None)
            monthly_stats["min"].append(None)
            monthly_stats["max"].append(None)
            monthly_stats["std"].append(None)
    return {"balance_type": balance_type, "region": region, "years": years, "yearly": yearly, "avg": avg, "range_min": range_min, "range_max": range_max, "monthly_stats": monthly_stats}


@app.get("/api/cb/heatmap")
async def cb_heatmap(balance_type: str = Query("total")):
    secs = _ensure_cb()
    if balance_type not in secs:
        raise HTTPException(400, f"Invalid balance_type: {balance_type}")
    sec = secs[balance_type]
    dates = sec["dates"]
    regions = list(sec["regions"].keys())
    # Build month labels (YYYY-MM)
    months = dates
    matrix = {}
    abs_max = 0.001
    for reg in regions:
        vals = sec["regions"][reg]
        matrix[reg] = {}
        for i, d in enumerate(dates):
            matrix[reg][d] = vals[i]
            if vals[i] is not None and abs(vals[i]) > abs_max:
                abs_max = abs(vals[i])
    return {"balance_type": balance_type, "regions": regions, "months": months, "matrix": matrix, "abs_max": abs_max}


@app.get("/api/cb/forecast")
async def cb_forecast(balance_type: str = Query("total"), region: str = Query("GLOBAL"), months: int = Query(6)):
    import math
    secs = _ensure_cb()
    if balance_type not in secs:
        raise HTTPException(400, f"Invalid balance_type: {balance_type}")
    vals = secs[balance_type]["regions"].get(region)
    dates = secs[balance_type]["dates"]
    if vals is None:
        raise HTTPException(400, f"Invalid region: {region}")
    valid = [(i, v) for i, v in enumerate(vals) if v is not None]
    if len(valid) < 6:
        raise HTTPException(400, "Not enough data to forecast")
    all_vals = [v for _, v in valid]
    n = len(all_vals)
    ma3 = sum(all_vals[-3:]) / 3
    ma3_fc = [round(ma3, 2)] * months
    ma6 = sum(all_vals[-6:]) / 6
    ma6_fc = [round(ma6, 2)] * months
    ma12 = sum(all_vals[-12:]) / min(12, n) if n >= 1 else 0
    ma12_fc = [round(ma12, 2)] * months
    monthly_avgs = {}
    for i, v in valid:
        mo = int(dates[i][5:7])
        if mo not in monthly_avgs:
            monthly_avgs[mo] = []
        monthly_avgs[mo].append(v)
    for mo in monthly_avgs:
        monthly_avgs[mo] = sum(monthly_avgs[mo]) / len(monthly_avgs[mo])
    last_date = dates[-1]
    last_yr, last_mo = int(last_date[:4]), int(last_date[5:7])
    seasonal_fc = []
    for m in range(months):
        fm = ((last_mo + m) % 12) + 1
        seasonal_fc.append(round(monthly_avgs.get(fm, ma3), 2))
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(all_vals) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, all_vals))
    den = sum((x - x_mean) ** 2 for x in xs)
    slope = num / den if den != 0 else 0
    intercept = y_mean - slope * x_mean
    trend_fc = [round(slope * (n + i) + intercept, 2) for i in range(months)]
    seasonal_trend_fc = []
    for m in range(months):
        fm = ((last_mo + m) % 12) + 1
        trend_val = slope * (n + m) + intercept
        seasonal_val = monthly_avgs.get(fm, 0)
        combined = (trend_val + seasonal_val) / 2
        seasonal_trend_fc.append(round(combined, 2))
    weights = [0.15, 0.15, 0.15, 0.25, 0.10, 0.20]
    all_methods = [ma3_fc, ma6_fc, ma12_fc, seasonal_fc, trend_fc, seasonal_trend_fc]
    ensemble_fc = []
    for m in range(months):
        val = sum(w * method[m] for w, method in zip(weights, all_methods))
        ensemble_fc.append(round(val, 2))
    fc_dates = []
    yr, mo = last_yr, last_mo
    for _ in range(months):
        mo += 1
        if mo > 12:
            mo = 1
            yr += 1
        fc_dates.append(f"{yr}-{mo:02d}")
    return {
        "balance_type": balance_type, "region": region,
        "historical_dates": dates, "historical_values": vals,
        "forecast_dates": fc_dates,
        "forecasts": {
            "ma3": ma3_fc,
            "ma6": ma6_fc,
            "ma12": ma12_fc,
            "seasonal": seasonal_fc,
            "trend": trend_fc,
            "seasonal_trend": seasonal_trend_fc,
            "ensemble": ensemble_fc,
        },
    }


@app.get("/api/cb/correlations")
async def cb_correlations():
    import math
    secs = _ensure_cb()
    series = {}
    for btype in ["sweet", "sour", "total"]:
        for region, vals in secs[btype]["regions"].items():
            key = f"{btype}_{region.lower().replace(' ', '_')}"
            label = f"{btype.upper()} {region}"
            series[key] = {"label": label, "values": vals}
    keys = list(series.keys())
    pairs = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            v1 = series[keys[i]]["values"]
            v2 = series[keys[j]]["values"]
            paired = [(a, b) for a, b in zip(v1, v2) if a is not None and b is not None]
            if len(paired) < 10:
                continue
            xs, ys = zip(*paired)
            n = len(xs)
            mx, my = sum(xs) / n, sum(ys) / n
            sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n) if n > 1 else 1
            sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n) if n > 1 else 1
            if sx == 0 or sy == 0:
                continue
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
            corr = cov / (sx * sy)
            pairs.append({
                "key1": keys[i], "key2": keys[j],
                "label1": series[keys[i]]["label"], "label2": series[keys[j]]["label"],
                "correlation": round(corr, 3), "abs_corr": round(abs(corr), 3),
            })
    pairs.sort(key=lambda p: p["abs_corr"], reverse=True)
    scatter_data = {}
    rolling_corr = {}
    dates = secs["sweet"]["dates"]
    for p in pairs[:15]:
        k = f"{p['key1']}__{p['key2']}"
        v1 = series[p["key1"]]["values"]
        v2 = series[p["key2"]]["values"]
        points = [{"x": a, "y": b, "date": dates[i]} for i, (a, b) in enumerate(zip(v1, v2)) if a is not None and b is not None]
        scatter_data[k] = {"points": points, "label1": p["label1"], "label2": p["label2"], "correlation": p["correlation"]}
        window = 12
        roll_dates, roll_vals = [], []
        for idx in range(window, len(v1)):
            w1 = [v1[j] for j in range(idx - window, idx) if v1[j] is not None and v2[j] is not None]
            w2 = [v2[j] for j in range(idx - window, idx) if v1[j] is not None and v2[j] is not None]
            if len(w1) < 6:
                continue
            nn = len(w1)
            mx2, my2 = sum(w1) / nn, sum(w2) / nn
            sx2 = math.sqrt(sum((x - mx2) ** 2 for x in w1) / nn)
            sy2 = math.sqrt(sum((y - my2) ** 2 for y in w2) / nn)
            if sx2 == 0 or sy2 == 0:
                roll_dates.append(dates[idx])
                roll_vals.append(0)
                continue
            cov2 = sum((x - mx2) * (y - my2) for x, y in zip(w1, w2)) / nn
            roll_dates.append(dates[idx])
            roll_vals.append(round(cov2 / (sx2 * sy2), 3))
        rolling_corr[k] = {"dates": roll_dates, "values": roll_vals}
    # Build frontend-expected format
    for p in pairs[:15]:
        p["key"] = f"{p['key1']}__{p['key2']}"
    scatter = {}
    rolling = {}
    for k, sd in scatter_data.items():
        scatter[k] = sd["points"]
    for k, rc in rolling_corr.items():
        rolling[k] = rc
    return {"pairs": pairs[:15], "scatter": scatter, "rolling": rolling}


@app.get("/api/cb/table")
async def cb_table():
    secs = _ensure_cb()
    dates = secs["sweet"]["dates"]
    rows = []
    for btype in ["sweet", "sour", "total"]:
        for region, vals in secs[btype]["regions"].items():
            valid = [v for v in vals if v is not None]
            rows.append({
                "balance_type": btype.upper(),
                "region": region,
                "latest": valid[-1] if valid else None,
                "avg": round(sum(valid) / len(valid), 2) if valid else None,
                "min": min(valid) if valid else None,
                "max": max(valid) if valid else None,
                "cum_sum": round(sum(valid), 2) if valid else None,
                "values": vals,
            })
    return {"dates": dates, "rows": rows}



# =====================================================================
#  EA BALANCES TAB
# =====================================================================
import json as _json

EA_DATA = {"loaded": False, "data": None}

def _default_ea_data():
    """Default EA data from Energy Aspects screenshot"""
    rows_raw = [
        {"metric": "Runs", "bold": True, "indent": 0, "y2025": 83.9, "q1_26": 82.9, "q2_26": 81.7, "q3_26": 85.6, "q4_26": 84.9, "y2026": 83.8, "q1_27": 85.1, "q2_27": 84.9, "q3_27": 85.6, "q4_27": 85.5, "y2027": 85.3, "yoy_26": -0.1, "yoy_27": 1.5},
        {"metric": "West of Suez", "bold": False, "indent": 1, "y2025": 43.1, "q1_26": 42.8, "q2_26": 43.0, "q3_26": 43.8, "q4_26": 43.2, "y2026": 43.2, "q1_27": 42.9, "q2_27": 43.1, "q3_27": 43.7, "q4_27": 43.2, "y2027": 43.2, "yoy_26": 0.1, "yoy_27": 0.0},
        {"metric": "East of Suez", "bold": False, "indent": 1, "y2025": 40.8, "q1_26": 40.1, "q2_26": 38.7, "q3_26": 41.8, "q4_26": 41.7, "y2026": 40.6, "q1_27": 42.3, "q2_27": 41.8, "q3_27": 42.0, "q4_27": 42.3, "y2027": 42.1, "yoy_26": -0.2, "yoy_27": 1.5},
        {"metric": "Crude burn + Other", "bold": True, "indent": 0, "y2025": 0.7, "q1_26": 0.6, "q2_26": 0.7, "q3_26": 0.8, "q4_26": 0.5, "y2026": 0.6, "q1_27": 0.5, "q2_27": 0.7, "q3_27": 0.8, "q4_27": 0.6, "y2027": 0.6, "yoy_26": 0.0, "yoy_27": 0.0},
        {"metric": "Non-OPEC total", "bold": True, "indent": 0, "y2025": 55.7, "q1_26": 55.8, "q2_26": 55.8, "q3_26": 56.4, "q4_26": 56.6, "y2026": 56.2, "q1_27": 56.5, "q2_27": 56.2, "q3_27": 56.4, "q4_27": 57.0, "y2027": 56.5, "yoy_26": 0.5, "yoy_27": 0.3},
        {"metric": "Non-OPEC excl NA", "bold": False, "indent": 1, "y2025": 34.3, "q1_26": 34.4, "q2_26": 34.5, "q3_26": 34.8, "q4_26": 35.1, "y2026": 34.7, "q1_27": 35.1, "q2_27": 35.1, "q3_27": 35.0, "q4_27": 35.5, "y2027": 35.2, "yoy_26": 0.4, "yoy_27": 0.4},
        {"metric": "North America", "bold": False, "indent": 1, "y2025": 21.3, "q1_26": 21.4, "q2_26": 21.2, "q3_26": 21.5, "q4_26": 21.5, "y2026": 21.4, "q1_27": 21.3, "q2_27": 21.2, "q3_27": 21.4, "q4_27": 21.4, "y2027": 21.3, "yoy_26": 0.1, "yoy_27": -0.1},
        {"metric": "FSU", "bold": False, "indent": 1, "y2025": 13.1, "q1_26": 12.8, "q2_26": 13.1, "q3_26": 13.1, "q4_26": 13.2, "y2026": 13.1, "q1_27": 13.1, "q2_27": 13.0, "q3_27": 13.0, "q4_27": 13.2, "y2027": 13.1, "yoy_26": 0.0, "yoy_27": 0.0},
        {"metric": "OPEC crude", "bold": True, "indent": 0, "y2025": 27.8, "q1_26": 26.5, "q2_26": 23.6, "q3_26": 28.4, "q4_26": 28.7, "y2026": 26.8, "q1_27": 28.9, "q2_27": 29.0, "q3_27": 29.1, "q4_27": 29.1, "y2027": 29.0, "yoy_26": -1.0, "yoy_27": 2.2},
        {"metric": "OPEC condensate", "bold": True, "indent": 0, "y2025": 2.1, "q1_26": 2.0, "q2_26": 1.8, "q3_26": 2.1, "q4_26": 2.2, "y2026": 2.0, "q1_27": 2.1, "q2_27": 2.1, "q3_27": 2.1, "q4_27": 2.1, "y2027": 2.1, "yoy_26": -0.1, "yoy_27": 0.1},
        {"metric": "Stock change", "bold": False, "indent": 0, "y2025": 1.0, "q1_26": 0.8, "q2_26": -1.3, "q3_26": 0.5, "q4_26": 2.1, "y2026": 0.5, "q1_27": 1.8, "q2_27": 1.8, "q3_27": 1.1, "q4_27": 2.1, "y2027": 1.7, "yoy_26": None, "yoy_27": None},
        {"metric": "of which commercial", "bold": True, "indent": 1, "italic": True, "y2025": 0.6, "q1_26": 0.4, "q2_26": 0.2, "q3_26": 1.2, "q4_26": 1.2, "y2026": 0.8, "q1_27": 1.0, "q2_27": 0.9, "q3_27": 0.8, "q4_27": 1.6, "y2027": 1.1, "yoy_26": None, "yoy_27": None},
        {"metric": "of which SPR", "bold": False, "indent": 1, "italic": True, "y2025": 0.4, "q1_26": 0.4, "q2_26": -1.5, "q3_26": -0.7, "q4_26": 0.9, "y2026": -0.2, "q1_27": 0.8, "q2_27": 0.9, "q3_27": 0.3, "q4_27": 0.5, "y2027": 0.6, "yoy_26": None, "yoy_27": None},
    ]
    return {
        "title": "Summary of crude and condensate balances, mb/d",
        "source": "internal",
        "columns": ["2025", "Q1 26", "Q2 26", "Q3 26", "Q4 26", "2026", "Q1 27", "Q2 27", "Q3 27", "Q4 27", "2027", "y/y 26", "y/y 27"],
        "col_keys": ["y2025", "q1_26", "q2_26", "q3_26", "q4_26", "y2026", "q1_27", "q2_27", "q3_27", "q4_27", "y2027", "yoy_26", "yoy_27"],
        "rows": rows_raw,
    }

if not _LEAN_MODE:
    EA_DATA["data"] = _default_ea_data()
    EA_DATA["loaded"] = True
    print("[EA-Bal] Loaded default EA Balances data")


def _generate_ea_trend_text(data):
    """Generate trend explanation for EA Balances"""
    rows = data["rows"]
    lines = []
    # Find latest quarter data - check Q1 27 as "latest forward"
    lines.append("**Latest Trend Analysis (Crude & Condensate Balances):**\n")
    
    # Runs analysis
    runs = next((r for r in rows if r["metric"] == "Runs"), None)
    if runs:
        q1_27 = runs.get("q1_27", 0)
        y2026 = runs.get("y2026", 0)
        chg = round(q1_27 - y2026, 1) if q1_27 and y2026 else 0
        direction = "higher" if chg > 0 else "lower"
        lines.append(f"• **Runs** are projected at {q1_27} mb/d in Q1 2027, {abs(chg)} mb/d {direction} than the 2026 average of {y2026} mb/d. Year-over-year change for 2027 is +{runs.get('yoy_27', 0)} mb/d, indicating {'strengthening' if (runs.get('yoy_27') or 0) > 0 else 'weakening'} refinery demand.")
    
    # Non-OPEC
    nopec = next((r for r in rows if r["metric"] == "Non-OPEC total"), None)
    if nopec:
        lines.append(f"• **Non-OPEC supply** is expected to grow modestly, from {nopec.get('y2026', 0)} mb/d in 2026 to {nopec.get('y2027', 0)} mb/d in 2027 (y/y +{nopec.get('yoy_27', 0)} mb/d).")
    
    # OPEC
    opec = next((r for r in rows if r["metric"] == "OPEC crude"), None)
    if opec:
        yoy = opec.get("yoy_27", 0) or 0
        lines.append(f"• **OPEC crude** production is forecast at {opec.get('y2027', 0)} mb/d for 2027, a significant y/y change of {'+' if yoy > 0 else ''}{yoy} mb/d from {opec.get('y2026', 0)} mb/d in 2026, suggesting {'unwinding of cuts' if yoy > 0 else 'deeper cuts'}.")
    
    # Stock change
    stk = next((r for r in rows if r["metric"] == "Stock change"), None)
    if stk:
        q_vals = [stk.get(f"q{i}_27", 0) or 0 for i in range(1, 5)]
        avg_build = sum(q_vals) / len(q_vals) if q_vals else 0
        lines.append(f"• **Stock changes** in 2027 average {round(avg_build, 1)} mb/d per quarter, implying a {'stock build (bearish)' if avg_build > 0 else 'stock draw (bullish)'} environment. Commercial stocks are projected to {'build' if (stk.get('y2027', 0) or 0) > 0 else 'draw'} by {abs(stk.get('y2027', 0) or 0)} mb/d on average.")
    
    # East vs West of Suez
    wos = next((r for r in rows if r["metric"] == "West of Suez"), None)
    eos = next((r for r in rows if r["metric"] == "East of Suez"), None)
    if wos and eos:
        wos_yoy = wos.get("yoy_27", 0) or 0
        eos_yoy = eos.get("yoy_27", 0) or 0
        if abs(eos_yoy) > abs(wos_yoy):
            lines.append(f"• **Regional split**: East of Suez runs show stronger y/y growth (+{eos_yoy} mb/d) vs West of Suez ({'+' if wos_yoy >= 0 else ''}{wos_yoy} mb/d), reflecting Asian refinery expansion.")
        else:
            lines.append(f"• **Regional split**: West of Suez runs ({'+' if wos_yoy >= 0 else ''}{wos_yoy} mb/d y/y) vs East of Suez ({'+' if eos_yoy >= 0 else ''}{eos_yoy} mb/d y/y).")
    
    return "\n".join(lines)


@app.get("/api/ea/data")
async def ea_get_data():
    if not EA_DATA["loaded"]:
        raise HTTPException(status_code=404, detail="EA data not loaded")
    d = EA_DATA["data"]
    trend = _generate_ea_trend_text(d)
    # Build chart data
    main_metrics = [r for r in d["rows"] if r["indent"] == 0 and r["metric"] not in ("Stock change",)]
    quarters = ["q1_26", "q2_26", "q3_26", "q4_26", "q1_27", "q2_27", "q3_27", "q4_27"]
    q_labels = ["Q1 26", "Q2 26", "Q3 26", "Q4 26", "Q1 27", "Q2 27", "Q3 27", "Q4 27"]
    chart_series = {}
    for r in d["rows"]:
        vals = [r.get(q) for q in quarters]
        chart_series[r["metric"]] = vals
    return {
        "title": d["title"],
        "source": d["source"],
        "columns": d["columns"],
        "col_keys": d["col_keys"],
        "rows": d["rows"],
        "trend_text": trend,
        "chart_quarters": q_labels,
        "chart_series": chart_series,
    }


@app.post("/api/ea/upload")
async def ea_upload(file: UploadFile = File(...)):
    """Upload EA balances Excel file. Expected format: same table structure as the screenshot."""
    import tempfile
    suffix = os.path.splitext(file.filename or "f.xlsx")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        raw = await file.read()
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        wb = openpyxl.load_workbook(tmp_path, data_only=True)
        ws = wb.active
        # Try to parse the table
        # Find header row with "2025" or year values
        header_row = None
        data_start_row = None
        for r in range(1, min(15, ws.max_row + 1)):
            for c in range(1, min(20, ws.max_column + 1)):
                v = ws.cell(r, c).value
                if v and str(v).strip() == "2025":
                    header_row = r
                    break
            if header_row:
                break
        if not header_row:
            raise HTTPException(status_code=400, detail="Could not find header row with '2025'")
        
        # Read column headers starting from header_row
        col_map = {}
        col_keys_list = []
        col_labels = []
        for c in range(2, ws.max_column + 1):
            v = ws.cell(header_row, c).value
            if v is None:
                # Check row above for year grouping and row below for quarter
                v_above = ws.cell(header_row - 1, c).value if header_row > 1 else None
                v_below = ws.cell(header_row + 1, c).value if header_row < ws.max_row else None
                if v_above:
                    v = v_above
            if v is not None:
                sv = str(v).strip()
                col_map[c] = sv
        
        # Read data rows
        rows_out = []
        metric_col = 1
        # Find first metric col
        for c in range(1, 5):
            v = ws.cell(header_row + 1, c).value
            if v and isinstance(v, str) and len(v) > 2:
                metric_col = c
                break
        
        for r in range(header_row + 1, ws.max_row + 1):
            metric = ws.cell(r, metric_col).value
            if metric is None:
                continue
            metric = str(metric).strip()
            if not metric or metric.lower().startswith("source"):
                continue
            row_data = {"metric": metric, "bold": False, "indent": 0}
            for c in range(metric_col + 1, ws.max_column + 1):
                v = ws.cell(r, c).value
                if v is not None:
                    try:
                        v = round(float(v), 1)
                    except (ValueError, TypeError):
                        v = None
                col_idx = c - (metric_col + 1)
                if col_idx < len(EA_DATA["data"]["col_keys"]):
                    row_data[EA_DATA["data"]["col_keys"][col_idx]] = v
            rows_out.append(row_data)
        
        if rows_out:
            EA_DATA["data"]["rows"] = rows_out
            EA_DATA["loaded"] = True
            return {"status": "ok", "rows": len(rows_out)}
        else:
            raise HTTPException(status_code=400, detail="No data rows found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)}")
    finally:
        os.unlink(tmp_path)


# =====================================================================
#  FGE BALANCES TAB
# =====================================================================

FGE_DATA = {"loaded": False, "sheets": {}, "dates": []}

def _parse_fge_excel(filepath):
    """Parse FGE Monthly Extended Global Oil Balance Tables"""
    wb = openpyxl.load_workbook(filepath, data_only=True)
    result = {}
    
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if ws.max_row < 3 or ws.max_column < 3:
            continue
        
        # Find dates row - look for datetime values
        date_row = None
        dates = []
        label_col = None
        type_col = None
        
        for r in range(1, min(10, ws.max_row + 1)):
            for c in range(1, min(ws.max_column + 1, 150)):
                v = ws.cell(r, c).value
                if v and hasattr(v, 'year'):
                    date_row = r
                    break
            if date_row:
                break
        
        if not date_row:
            continue
        
        # Read dates
        data_start_col = None
        for c in range(1, min(ws.max_column + 1, 150)):
            v = ws.cell(date_row, c).value
            if v and hasattr(v, 'year'):
                if data_start_col is None:
                    data_start_col = c
                dates.append(v.strftime("%Y-%m"))
        
        if not dates or not data_start_col:
            continue
        
        # Find label columns
        # Check which cols before data_start_col have labels
        label_cols = []
        for c in range(1, data_start_col):
            has_data = False
            for r in range(date_row + 1, min(date_row + 5, ws.max_row + 1)):
                if ws.cell(r, c).value is not None:
                    has_data = True
                    break
            if has_data:
                label_cols.append(c)
        
        # Read section header (row above dates or title row)
        section_title = None
        for r in range(max(1, date_row - 3), date_row):
            for c in range(1, data_start_col):
                v = ws.cell(r, c).value
                if v and isinstance(v, str) and len(v) > 5:
                    section_title = v
                    break
        
        # Read data rows
        rows = []
        for r in range(date_row + 1, ws.max_row + 1):
            # Get labels - only use text labels, skip numeric-only columns
            labels = []
            for c in label_cols:
                v = ws.cell(r, c).value
                if v is not None:
                    sv = str(v).strip()
                    # Skip pure numeric values in label cols
                    try:
                        float(sv)
                        continue
                    except ValueError:
                        pass
                    # Skip datetime values
                    if hasattr(v, 'year'):
                        continue
                    labels.append(sv)
            
            if not labels:
                continue
            
            # Use only first meaningful label (avoid concatenating noise)
            label = labels[0]
            # Truncate very long labels
            if len(label) > 80:
                label = label[:77] + "..."
            
            # Get values
            values = []
            has_numeric = False
            for i, d in enumerate(dates):
                c = data_start_col + i
                v = ws.cell(r, c).value
                if v is not None:
                    try:
                        v = round(float(v), 2)
                        has_numeric = True
                    except (ValueError, TypeError):
                        v = None
                values.append(v)
            
            if has_numeric:
                rows.append({"label": label, "values": values})
        
        if rows:
            result[sheet_name] = {
                "title": section_title or sheet_name,
                "dates": dates,
                "rows": rows,
            }
    
    return result


def _generate_fge_trend_text(sheet_data):
    """Generate trend explanation for an FGE sheet"""
    rows = sheet_data.get("rows", [])
    dates = sheet_data.get("dates", [])
    if not rows or not dates:
        return "No data available for trend analysis."
    
    lines = []
    title = sheet_data.get("title", "FGE Data")
    lines.append(f"**Latest Trend Analysis — {title}:**\n")
    
    # Find the latest month with actual data (March 2026 = current)
    # Find latest non-None values
    latest_idx = len(dates) - 1
    
    # Analyze top rows (usually the most important metrics)
    for row in rows[:min(12, len(rows))]:
        label = row["label"]
        vals = row["values"]
        
        # Find latest value
        latest_val = None
        latest_i = None
        for i in range(len(vals) - 1, -1, -1):
            if vals[i] is not None:
                latest_val = vals[i]
                latest_i = i
                break
        
        if latest_val is None or latest_i is None:
            continue
        
        # Find previous value
        prev_val = None
        for i in range(latest_i - 1, -1, -1):
            if vals[i] is not None:
                prev_val = vals[i]
                break
        
        # YoY comparison (12 months back)
        yoy_val = None
        if latest_i >= 12 and vals[latest_i - 12] is not None:
            yoy_val = vals[latest_i - 12]
        
        latest_date = dates[latest_i] if latest_i < len(dates) else "latest"
        
        chg_text = ""
        if prev_val is not None:
            chg = round(latest_val - prev_val, 1)
            pct = round(100 * chg / abs(prev_val), 1) if prev_val != 0 else 0
            direction = "up" if chg > 0 else "down" if chg < 0 else "flat"
            chg_text = f" ({direction} {abs(chg):,.1f}, {abs(pct):.1f}% m/m)"
        
        yoy_text = ""
        if yoy_val is not None:
            yoy_chg = round(latest_val - yoy_val, 1)
            direction = "higher" if yoy_chg > 0 else "lower" if yoy_chg < 0 else "flat"
            yoy_text = f", {abs(yoy_chg):,.1f} {direction} y/y"
        
        lines.append(f"• **{label}**: {latest_val:,.1f} as of {latest_date}{chg_text}{yoy_text}")
    
    # Summary
    if len(rows) > 12:
        lines.append(f"\n*Showing top 12 of {len(rows)} metrics. Full data available in the table view.*")
    
    return "\n".join(lines)


# Load FGE data on startup
_fge_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "fge_balances.xlsm")
if _LEAN_MODE:
    print("[FGE] LEAN_MODE — skipping FGE data load")
elif os.path.exists(_fge_path):
    try:
        FGE_DATA["sheets"] = _parse_fge_excel(_fge_path)
        FGE_DATA["loaded"] = True
        print(f"[FGE] Loaded {len(FGE_DATA['sheets'])} sheets: {list(FGE_DATA['sheets'].keys())}")
        for sn, sd in FGE_DATA["sheets"].items():
            print(f"  [{sn}] {len(sd['rows'])} rows, {len(sd['dates'])} months")
    except Exception as e:
        print(f"[FGE] Error loading: {e}")
else:
    print(f"[FGE] File not found: {_fge_path}")


@app.get("/api/fge/sheets")
async def fge_list_sheets():
    if not FGE_DATA["loaded"]:
        raise HTTPException(status_code=404, detail="FGE data not loaded")
    sheets = []
    for name, data in FGE_DATA["sheets"].items():
        sheets.append({
            "name": name,
            "title": data["title"],
            "rows": len(data["rows"]),
            "months": len(data["dates"]),
        })
    return {"sheets": sheets}


@app.get("/api/fge/sheet/{sheet_name}")
async def fge_get_sheet(sheet_name: str):
    if not FGE_DATA["loaded"]:
        raise HTTPException(status_code=404, detail="FGE data not loaded")
    if sheet_name not in FGE_DATA["sheets"]:
        raise HTTPException(status_code=404, detail=f"Sheet '{sheet_name}' not found")
    sd = FGE_DATA["sheets"][sheet_name]
    trend = _generate_fge_trend_text(sd)
    
    # Build chart data for top metrics
    chart_metrics = []
    for row in sd["rows"][:20]:
        vals = row["values"]
        valid = [(i, v) for i, v in enumerate(vals) if v is not None]
        if len(valid) >= 6:
            chart_metrics.append({
                "label": row["label"],
                "values": vals,
            })
    
    return {
        "title": sd["title"],
        "dates": sd["dates"],
        "rows": sd["rows"],
        "trend_text": trend,
        "chart_metrics": chart_metrics[:15],
    }


@app.get("/api/fge/compare")
async def fge_compare(sheet: str, metrics: str):
    """Compare multiple metrics from a sheet. metrics = comma-separated labels."""
    if not FGE_DATA["loaded"]:
        raise HTTPException(status_code=404, detail="FGE data not loaded")
    if sheet not in FGE_DATA["sheets"]:
        raise HTTPException(status_code=404, detail=f"Sheet '{sheet}' not found")
    sd = FGE_DATA["sheets"][sheet]
    metric_list = [m.strip() for m in metrics.split(",")]
    series = {}
    for row in sd["rows"]:
        if row["label"] in metric_list:
            series[row["label"]] = row["values"]
    return {"dates": sd["dates"], "series": series}


@app.post("/api/fge/upload")
async def fge_upload(file: UploadFile = File(...)):
    """Upload new FGE balances Excel file (same format)"""
    import tempfile
    suffix = os.path.splitext(file.filename or "f.xlsx")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        raw = await file.read()
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        sheets = _parse_fge_excel(tmp_path)
        if not sheets:
            raise HTTPException(status_code=400, detail="No valid sheets found in uploaded file")
        FGE_DATA["sheets"] = sheets
        FGE_DATA["loaded"] = True
        # Save to project dir
        dest = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "fge_balances.xlsm")
        import shutil
        shutil.copy2(tmp_path, dest)
        return {"status": "ok", "sheets": len(sheets), "sheet_names": list(sheets.keys())}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)}")
    finally:
        os.unlink(tmp_path)



# =====================================================================
#  REGIME IDENTIFICATION (Entropy-based)
# =====================================================================

def _compute_regime(prices, window=60, n_bins=10):
    """
    Compute entropy-based regime identification.
    - Takes daily prices
    - Computes log returns
    - Rolling window: discretize returns into bins, estimate probabilities, compute Shannon entropy
    - Low entropy = predictable/trending, High entropy = chaotic/unpredictable
    """
    import math
    
    if len(prices) < window + 5:
        return None
    
    # Compute log returns
    returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0 and prices[i] > 0:
            returns.append(math.log(prices[i] / prices[i - 1]))
        else:
            returns.append(0.0)
    
    # Global min/max for bin edges
    valid_rets = [r for r in returns if abs(r) < 0.5]  # filter outliers
    if not valid_rets:
        return None
    
    r_min = min(valid_rets)
    r_max = max(valid_rets)
    if r_max <= r_min:
        return None
    
    bin_width = (r_max - r_min) / n_bins
    max_entropy = math.log(n_bins)  # maximum possible entropy
    
    # Rolling entropy computation
    entropy_series = []
    regime_labels = []
    
    for i in range(window - 1, len(returns)):
        window_returns = returns[i - window + 1:i + 1]
        
        # Discretize into bins
        counts = [0] * n_bins
        for r in window_returns:
            b = int((r - r_min) / bin_width)
            b = max(0, min(n_bins - 1, b))
            counts[b] += 1
        
        # Compute probabilities and Shannon entropy
        total = sum(counts)
        entropy = 0.0
        for c in counts:
            if c > 0:
                p = c / total
                entropy -= p * math.log(p)
        
        # Normalize entropy (0 = perfectly predictable, 1 = max chaos)
        norm_entropy = entropy / max_entropy if max_entropy > 0 else 0
        entropy_series.append(round(norm_entropy, 4))
        
        # Classify regime
        if norm_entropy < 0.55:
            regime_labels.append("Low Entropy (Trending)")
        elif norm_entropy < 0.75:
            regime_labels.append("Medium Entropy (Transitional)")
        else:
            regime_labels.append("High Entropy (Chaotic)")
    
    return {
        "entropy": entropy_series,
        "regimes": regime_labels,
        "offset": window,  # first entropy value corresponds to price index = window
    }


def _compute_additional_regime_metrics(prices, returns_offset=1):
    """Compute additional regime metrics: volatility clustering, trend strength, mean reversion score"""
    import math
    
    n = len(prices)
    if n < 60:
        return {}
    
    # Returns
    rets = []
    for i in range(1, n):
        if prices[i - 1] > 0 and prices[i] > 0:
            rets.append(math.log(prices[i] / prices[i - 1]))
        else:
            rets.append(0.0)
    
    # Rolling volatility (20-day)
    vol_window = 20
    rolling_vol = []
    for i in range(vol_window - 1, len(rets)):
        w = rets[i - vol_window + 1:i + 1]
        mean_w = sum(w) / len(w)
        var_w = sum((x - mean_w) ** 2 for x in w) / len(w)
        rolling_vol.append(round(math.sqrt(var_w) * math.sqrt(252) * 100, 2))  # annualized %
    
    # Trend strength (ADX-like: ratio of net move to total move over 20 days)
    trend_window = 20
    trend_strength = []
    for i in range(trend_window, n):
        net_move = abs(prices[i] - prices[i - trend_window])
        total_move = sum(abs(prices[j] - prices[j - 1]) for j in range(i - trend_window + 1, i + 1))
        ts = round(net_move / total_move, 4) if total_move > 0 else 0
        trend_strength.append(ts)
    
    # Hurst exponent approximation (R/S method over rolling window)
    hurst_window = 60
    hurst_values = []
    for i in range(hurst_window, len(rets)):
        w = rets[i - hurst_window:i]
        mean_w = sum(w) / len(w)
        # Cumulative deviations
        cum_dev = []
        s = 0
        for x in w:
            s += (x - mean_w)
            cum_dev.append(s)
        R = max(cum_dev) - min(cum_dev)
        S = math.sqrt(sum((x - mean_w) ** 2 for x in w) / len(w))
        if S > 0 and R > 0:
            # H ≈ log(R/S) / log(n)
            H = round(math.log(R / S) / math.log(len(w)), 4)
            H = max(0, min(1, H))
        else:
            H = 0.5
        hurst_values.append(H)
    
    return {
        "rolling_vol": rolling_vol,
        "vol_offset": vol_window,
        "trend_strength": trend_strength,
        "trend_offset": trend_window,
        "hurst": hurst_values,
        "hurst_offset": hurst_window + 1,
    }


@app.get("/api/regime/{instrument_id}")
async def get_regime(instrument_id: str, timeframe: str = "Daily", window: int = 60, n_bins: int = 10):
    """Compute entropy-based regime identification for an instrument"""
    if instrument_id not in instruments:
        raise HTTPException(status_code=404, detail="Instrument not found")
    
    inst = instruments[instrument_id]
    if timeframe not in inst["timeframes"]:
        raise HTTPException(status_code=404, detail=f"Timeframe '{timeframe}' not found")
    
    tf_data = inst["timeframes"][timeframe]
    # Extract dates and prices from the data array
    raw_data = tf_data.get("data", [])
    dates = [d.get("date", "") for d in raw_data]
    prices = [d.get("price", 0) for d in raw_data if d.get("price") is not None]
    # Align dates to only those with valid prices
    dates = [d.get("date", "") for d in raw_data if d.get("price") is not None]
    
    if not prices:
        raise HTTPException(status_code=400, detail="No price data in this timeframe")
    
    # Compute regime
    regime_result = _compute_regime(prices, window=window, n_bins=n_bins)
    if regime_result is None:
        raise HTTPException(status_code=400, detail="Not enough data for regime analysis")
    
    # Compute additional metrics
    additional = _compute_additional_regime_metrics(prices)
    
    # Build time series for chart
    offset = regime_result["offset"]
    chart_data = []
    for i, (ent, reg) in enumerate(zip(regime_result["entropy"], regime_result["regimes"])):
        idx = offset + i
        if idx < len(dates) and idx < len(prices):
            chart_data.append({
                "date": dates[idx],
                "price": round(prices[idx], 2),
                "entropy": ent,
                "regime": reg,
            })
    
    # Current regime summary
    if chart_data:
        latest = chart_data[-1]
        # Count regime durations
        current_regime = latest["regime"]
        streak = 0
        for pt in reversed(chart_data):
            if pt["regime"] == current_regime:
                streak += 1
            else:
                break
        
        # Regime distribution
        regime_counts = {}
        for pt in chart_data:
            r = pt["regime"]
            regime_counts[r] = regime_counts.get(r, 0) + 1
        total = len(chart_data)
        regime_dist = {k: round(v / total * 100, 1) for k, v in regime_counts.items()}
        
        # Average entropy
        avg_entropy = round(sum(pt["entropy"] for pt in chart_data) / len(chart_data), 4)
        
        summary = {
            "current_regime": current_regime,
            "current_entropy": latest["entropy"],
            "current_price": latest["price"],
            "regime_streak_days": streak,
            "avg_entropy": avg_entropy,
            "regime_distribution": regime_dist,
        }
    else:
        summary = {}
    
    # Build vol/trend/hurst chart data
    vol_chart = []
    if "rolling_vol" in additional:
        vo = additional["vol_offset"]
        for i, v in enumerate(additional["rolling_vol"]):
            idx = vo + i
            if idx < len(dates):
                vol_chart.append({"date": dates[idx], "volatility": v})
    
    trend_chart = []
    if "trend_strength" in additional:
        to = additional["trend_offset"]
        for i, v in enumerate(additional["trend_strength"]):
            idx = to + i
            if idx < len(dates):
                trend_chart.append({"date": dates[idx], "trend_strength": round(v * 100, 1)})
    
    hurst_chart = []
    if "hurst" in additional:
        ho = additional["hurst_offset"]
        for i, v in enumerate(additional["hurst"]):
            idx = ho + i
            if idx < len(dates):
                hurst_chart.append({"date": dates[idx], "hurst": v})
    
    # Generate insight text
    insight_lines = []
    if summary:
        insight_lines.append(f"**Current Market Regime: {summary['current_regime']}**\n")
        insight_lines.append(f"The market has been in the current regime for **{summary['regime_streak_days']} periods**.")
        
        ent = summary["current_entropy"]
        if ent < 0.55:
            insight_lines.append("Low entropy indicates the market is in a **structured, predictable state**. Returns are concentrated in fewer bins — the market has 'chosen a direction'. This is typically a trending environment favorable for momentum/trend-following strategies.")
        elif ent < 0.75:
            insight_lines.append("Medium entropy suggests the market is in a **transitional phase**. Neither strongly trending nor fully chaotic. Caution advised — regime shifts are more likely in this zone.")
        else:
            insight_lines.append("High entropy indicates the market is in a **chaotic, unpredictable state**. Returns are evenly distributed across outcomes — no single direction dominates. Mean-reversion strategies may work better, but sizing should be reduced.")
        
        if hurst_chart:
            latest_hurst = hurst_chart[-1]["hurst"]
            if latest_hurst > 0.55:
                insight_lines.append(f"\nHurst exponent: **{latest_hurst:.3f}** (>0.5 = trending/persistent behavior)")
            elif latest_hurst < 0.45:
                insight_lines.append(f"\nHurst exponent: **{latest_hurst:.3f}** (<0.5 = mean-reverting behavior)")
            else:
                insight_lines.append(f"\nHurst exponent: **{latest_hurst:.3f}** (~0.5 = random walk)")
        
        insight_lines.append(f"\n**Regime Distribution:** " + ", ".join(f"{k}: {v}%" for k, v in summary["regime_distribution"].items()))
    
    return {
        "instrument": inst["name"],
        "timeframe": timeframe,
        "window": window,
        "n_bins": n_bins,
        "chart_data": chart_data,
        "summary": summary,
        "vol_chart": vol_chart,
        "trend_chart": trend_chart,
        "hurst_chart": hurst_chart,
        "insight": "\n".join(insight_lines),
    }


# =====================================================================
#  RISK ASSESSMENT ENGINE
# =====================================================================

@app.post("/api/risk/calculate")
async def risk_calculate(request: dict):
    """
    Risk Assessment Engine - calculates position sizing, layered execution,
    and profit targets based on institutional protocols.
    """
    import math
    
    # Extract inputs
    asset = request.get("asset", "Unknown")
    direction = request.get("direction", "LONG").upper()
    total_capital = float(request.get("total_capital", 10000))
    risk_pct = float(request.get("risk_pct", 1.0))
    entry_price = float(request.get("entry_price", 0))
    stop_loss = float(request.get("stop_loss", 0))
    setup_grade = request.get("setup_grade", "B")
    
    if entry_price <= 0 or stop_loss <= 0:
        raise HTTPException(status_code=400, detail="Entry price and stop loss must be positive")
    
    # Validate direction consistency
    if direction == "LONG" and stop_loss >= entry_price:
        raise HTTPException(status_code=400, detail="For LONG trades, stop loss must be below entry price")
    if direction == "SHORT" and stop_loss <= entry_price:
        raise HTTPException(status_code=400, detail="For SHORT trades, stop loss must be above entry price")
    
    # Core calculations
    sl_distance = abs(entry_price - stop_loss)
    sl_distance_pct = round(sl_distance / entry_price * 100, 2)
    max_capital_loss = round(total_capital * risk_pct / 100, 2)
    risk_exposure_pct = risk_pct
    
    # Position size (in units)
    position_size = round(max_capital_loss / sl_distance, 4) if sl_distance > 0 else 0
    position_value = round(position_size * entry_price, 2)
    
    # Layered Entry (DCA) - 3 layers: 50%, 30%, 20%
    layer_pcts = [0.50, 0.30, 0.20]
    layer_names = ["Layer 1 (50%)", "Layer 2 (30%)", "Layer 3 (20%)"]
    
    if direction == "LONG":
        # Layer deeper entries (slightly below entry)
        layer_prices = [
            round(entry_price, 2),
            round(entry_price - sl_distance * 0.25, 2),
            round(entry_price - sl_distance * 0.50, 2),
        ]
    else:
        layer_prices = [
            round(entry_price, 2),
            round(entry_price + sl_distance * 0.25, 2),
            round(entry_price + sl_distance * 0.50, 2),
        ]
    
    layers = []
    avg_entry = 0
    for i in range(3):
        units = round(position_size * layer_pcts[i], 4)
        avg_entry += layer_prices[i] * layer_pcts[i]
        layers.append({
            "name": layer_names[i],
            "price": layer_prices[i],
            "units": units,
            "pct": int(layer_pcts[i] * 100),
        })
    avg_entry = round(avg_entry, 2)
    
    # Setup Grade multipliers for R:R targets
    grade_multipliers = {
        "A+": [2.0, 3.0, 4.0],
        "A": [2.0, 3.0, 4.0],
        "B": [1.5, 2.0, 3.0],
        "C": [1.0, 1.5, 2.0],
        "D+": [1.0, 1.5, 2.0],
        "D": [0.8, 1.0, 1.5],
    }
    rr_targets = grade_multipliers.get(setup_grade, [1.5, 2.0, 3.0])
    
    # Take Profit targets
    tp_pcts = [0.50, 0.30, 0.20]  # Close 50% at TP1, 30% at TP2, 20% at TP3
    take_profits = []
    total_profit = 0
    
    for i, (rr, close_pct) in enumerate(zip(rr_targets, tp_pcts)):
        if direction == "LONG":
            tp_price = round(avg_entry + sl_distance * rr, 2)
        else:
            tp_price = round(avg_entry - sl_distance * rr, 2)
        
        tp_units = round(position_size * close_pct, 4)
        tp_profit = round(abs(tp_price - avg_entry) * tp_units, 2)
        total_profit += tp_profit
        
        take_profits.append({
            "name": f"TP {i + 1} ({int(close_pct * 100)}%)",
            "price": tp_price,
            "units": tp_units,
            "rr": f"1:{rr}",
            "profit": tp_profit,
        })
    
    total_profit = round(total_profit, 2)
    overall_rr = round(total_profit / max_capital_loss, 1) if max_capital_loss > 0 else 0
    account_growth = round(total_profit / total_capital * 100, 2)
    
    # Determine grade description
    grade_desc = {
        "A+": "Threvio Edge — Maximum conviction setup",
        "A": "High-probability institutional setup",
        "B": "Standard setup with good structure",
        "C": "Below average — reduced sizing recommended",
        "D+": "Marginal — proceed with extreme caution",
        "D": "Weak setup — consider skipping",
    }
    
    # Risk assessment summary
    if overall_rr >= 2.0:
        risk_verdict = "FAVORABLE"
        risk_color = "green"
    elif overall_rr >= 1.5:
        risk_verdict = "ACCEPTABLE"
        risk_color = "yellow"
    else:
        risk_verdict = "UNFAVORABLE"
        risk_color = "red"
    
    return {
        "asset": asset,
        "direction": direction,
        "setup_grade": setup_grade,
        "setup_grade_desc": grade_desc.get(setup_grade, ""),
        "total_capital": total_capital,
        "risk_pct": risk_pct,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "avg_entry": avg_entry,
        "sl_distance": round(sl_distance, 2),
        "sl_distance_pct": sl_distance_pct,
        "max_capital_loss": max_capital_loss,
        "risk_exposure_pct": risk_exposure_pct,
        "position_size": position_size,
        "position_value": position_value,
        "layers": layers,
        "take_profits": take_profits,
        "total_profit": total_profit,
        "overall_rr": f"1:{overall_rr}",
        "overall_rr_num": overall_rr,
        "account_growth": account_growth,
        "risk_verdict": risk_verdict,
        "risk_color": risk_color,
    }


@app.get("/api/risk/instrument/{instrument_id}")
async def risk_instrument_info(instrument_id: str, timeframe: str = "Daily"):
    """Get current price and volatility info for pre-filling risk calculator"""
    if instrument_id not in instruments:
        raise HTTPException(status_code=404, detail="Instrument not found")
    
    inst = instruments[instrument_id]
    if timeframe not in inst["timeframes"]:
        raise HTTPException(status_code=404, detail=f"Timeframe '{timeframe}' not found")
    
    tf_data = inst["timeframes"][timeframe]
    raw_data = tf_data.get("data", [])
    prices = [d.get("price", 0) for d in raw_data if d.get("price") is not None]
    
    if not prices:
        raise HTTPException(status_code=400, detail="No price data")
    
    import math
    
    latest_price = prices[-1]
    
    # ATR-like volatility (average true range over 14 periods)
    atr_period = min(14, len(prices) - 1)
    ranges = []
    for i in range(len(prices) - atr_period, len(prices)):
        if i > 0:
            ranges.append(abs(prices[i] - prices[i - 1]))
    avg_range = sum(ranges) / len(ranges) if ranges else 0
    
    # Suggested stop loss distances (1x ATR, 1.5x ATR, 2x ATR)
    suggested_sl = {
        "tight": round(avg_range, 2),
        "normal": round(avg_range * 1.5, 2),
        "wide": round(avg_range * 2, 2),
    }
    
    return {
        "name": inst["name"],
        "latest_price": round(latest_price, 2),
        "avg_range": round(avg_range, 2),
        "suggested_sl": suggested_sl,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ═══  MONEY POSITIONING ANALYSIS (OIES Insight 177)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_co_price_data(filepath: str):
    """Load CO1/CO2 price, volume, and open interest data from COTnew.xlsx."""
    global co_price_data
    for contract in ["CO1", "CO2"]:
        try:
            df = pd.read_excel(filepath, sheet_name=contract)
            df.columns = [str(c).strip() for c in df.columns]
            date_col = df.columns[0]
            price_col = [c for c in df.columns if "Last Price" in c or "Price" in c]
            oi_col = [c for c in df.columns if "Open Interest" in c]
            vol_col = [c for c in df.columns if "Volume" in c]

            records = []
            for _, row in df.iterrows():
                d = row[date_col]
                if pd.isna(d):
                    continue
                if isinstance(d, datetime):
                    ds = d.strftime("%Y-%m-%d")
                else:
                    try:
                        ds = pd.to_datetime(str(d)).strftime("%Y-%m-%d")
                    except Exception:
                        continue
                rec = {"date": ds}
                if price_col:
                    v = row[price_col[0]]
                    rec["price"] = float(v) if pd.notna(v) else None
                if oi_col:
                    v = row[oi_col[0]]
                    rec["open_interest"] = float(v) if pd.notna(v) else None
                if vol_col:
                    v = row[vol_col[0]]
                    rec["volume"] = float(v) if pd.notna(v) else None
                records.append(rec)

            co_price_data[contract] = records
            print(f"[STARTUP] Loaded {contract} data: {len(records)} rows")
        except Exception as e:
            print(f"[STARTUP] Failed to load {contract}: {e}")


def _compute_money_positioning():
    """
    Implement OIES Insight 177 Money Positioning analysis.
    Decompose Managed Money into slow (1yr MA) and fast (z-score) components.
    Compute momentum signals at multiple lookback horizons.
    """
    if "categories" not in cot_data or "Managed Money" not in cot_data["categories"]:
        return None

    mm_cat = cot_data["categories"]["Managed Money"]
    mm_rows = mm_cat["data"]
    if not mm_rows:
        return None

    # Build DataFrame
    records = []
    for r in mm_rows:
        records.append({
            "date": r["date"],
            "long": r.get("Long", r.get("long", 0)),
            "short": r.get("Short", r.get("short", 0)),
            "net": r.get("Net", r.get("net", 0)),
            "spreading": r.get("Spreading", r.get("spreading", 0)),
        })
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["net"] = pd.to_numeric(df["net"], errors="coerce")
    df["long"] = pd.to_numeric(df["long"], errors="coerce")
    df["short"] = pd.to_numeric(df["short"], errors="coerce")
    df["spreading"] = pd.to_numeric(df["spreading"], errors="coerce")

    # Slow-Fast Decomposition (Section 2.2 of paper)
    # Slow = 52-week (approx 1 year) rolling mean of net positions
    # Fast = z-score: (MM - MA_52w(MM)) / σ_52w(MM)
    window = 52  # weekly data -> 52 weeks = 1 year
    df["slow_component"] = df["net"].rolling(window=window, min_periods=10).mean()
    rolling_std = df["net"].rolling(window=window, min_periods=10).std()
    df["fast_component"] = (df["net"] - df["slow_component"]) / rolling_std.replace(0, np.nan)
    # Percentile of net position over full history
    df["net_percentile"] = df["net"].rank(pct=True) * 100

    # Long-short ratio
    df["ls_ratio"] = df["long"] / df["short"].replace(0, np.nan)

    # Weekly changes
    df["net_change_1w"] = df["net"].diff()
    df["net_change_4w"] = df["net"].diff(4)

    # Build CO1 price series aligned to COT dates for momentum
    co1_prices = None
    if "CO1" in co_price_data and co_price_data["CO1"]:
        co1_df = pd.DataFrame(co_price_data["CO1"])
        co1_df["date"] = pd.to_datetime(co1_df["date"])
        co1_df = co1_df.sort_values("date")
        co1_df = co1_df.dropna(subset=["price"])
        co1_prices = co1_df.set_index("date")["price"]

    # Momentum signals at multiple lookback horizons (Section 2.1 of paper)
    momentum_signals = {}
    if co1_prices is not None and len(co1_prices) > 50:
        # Compute cumulative P&L (to deseasonalize per paper)
        pnl = co1_prices.diff().cumsum().fillna(0)
        vol_60d = co1_prices.diff().rolling(60).std()

        for n in [5, 10, 20, 50, 100, 150, 200, 250]:
            ma_n = pnl.rolling(n, min_periods=max(1, n // 2)).mean()
            mom = (pnl - ma_n) / vol_60d.replace(0, np.nan)
            # Second normalization: rolling 1yr std of MOM
            mom_std = mom.rolling(250, min_periods=50).std()
            x_n = mom / mom_std.replace(0, np.nan)
            momentum_signals[n] = x_n

    # Reaction function R(u) = u * exp((1 - u^2) / 2)
    def reaction(u):
        return u * np.exp((1 - u**2) / 2)

    # Composite trend-following score (average of reaction across horizons)
    trend_score = None
    if momentum_signals:
        scores = []
        for n, sig in momentum_signals.items():
            scores.append(reaction(sig))
        trend_score = pd.concat(scores, axis=1).mean(axis=1)

    # Build Momentum vs Positioning overlay (aligned to COT dates)
    momentum_overlay = []
    if trend_score is not None:
        for _, row in df.iterrows():
            d = row["date"]
            # Find nearest daily trend score
            nearest_idx = trend_score.index.searchsorted(d)
            if nearest_idx > 0 and nearest_idx <= len(trend_score):
                idx = min(nearest_idx, len(trend_score) - 1)
                momentum_overlay.append({
                    "date": d.strftime("%Y-%m-%d"),
                    "trend_score": round(float(trend_score.iloc[idx]), 4) if pd.notna(trend_score.iloc[idx]) else None,
                    "fast_component": round(float(row["fast_component"]), 4) if pd.notna(row["fast_component"]) else None,
                })

    # Build result
    decomposition = []
    for _, row in df.iterrows():
        decomposition.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "net_position": int(row["net"]) if pd.notna(row["net"]) else None,
            "long": int(row["long"]) if pd.notna(row["long"]) else None,
            "short": int(row["short"]) if pd.notna(row["short"]) else None,
            "spreading": int(row["spreading"]) if pd.notna(row["spreading"]) else None,
            "slow_component": round(float(row["slow_component"]), 0) if pd.notna(row["slow_component"]) else None,
            "fast_component": round(float(row["fast_component"]), 4) if pd.notna(row["fast_component"]) else None,
            "net_percentile": round(float(row["net_percentile"]), 1) if pd.notna(row["net_percentile"]) else None,
            "ls_ratio": round(float(row["ls_ratio"]), 2) if pd.notna(row["ls_ratio"]) else None,
            "net_change_1w": int(row["net_change_1w"]) if pd.notna(row["net_change_1w"]) else None,
            "net_change_4w": int(row["net_change_4w"]) if pd.notna(row["net_change_4w"]) else None,
        })

    # Summary stats
    latest = decomposition[-1] if decomposition else {}
    prev = decomposition[-2] if len(decomposition) > 1 else {}

    return {
        "decomposition": decomposition,
        "momentum_overlay": momentum_overlay,
        "summary": {
            "latest_date": latest.get("date"),
            "net_position": latest.get("net_position"),
            "slow_component": latest.get("slow_component"),
            "fast_component": latest.get("fast_component"),
            "net_percentile": latest.get("net_percentile"),
            "ls_ratio": latest.get("ls_ratio"),
            "weekly_change": latest.get("net_change_1w"),
            "monthly_change": latest.get("net_change_4w"),
            "prev_fast": prev.get("fast_component"),
        },
        "methodology": {
            "paper": "OIES Energy Insight 177 - Momentum Trading and Managed Money Positioning in Energy (March 2026)",
            "authors": "Wu-Yen Sun (KAPSARC), Ilia Bouchouev (Pentathlon/OIES), Bassam Fattouh (OIES)",
            "approach": "Slow-fast decomposition: slow = 52-week MA of Managed Money net positions (pension/long-only); fast = z-score (CTA trend-following). Momentum signals computed using cumulative P&L deviations from moving averages, normalized by volatility. Reaction function R(u) = u*exp((1-u²)/2) models CTA behavior with attenuation at extremes.",
            "lookback_horizons": [5, 10, 20, 50, 100, 150, 200, 250],
        }
    }


def _compute_contract_analysis():
    """Analyze CO1 vs CO2 price, volume, and open interest dynamics."""
    if not co_price_data.get("CO1") or not co_price_data.get("CO2"):
        return None

    co1_df = pd.DataFrame(co_price_data["CO1"])
    co2_df = pd.DataFrame(co_price_data["CO2"])
    co1_df["date"] = pd.to_datetime(co1_df["date"])
    co2_df["date"] = pd.to_datetime(co2_df["date"])
    co1_df = co1_df.sort_values("date")
    co2_df = co2_df.sort_values("date")

    # Merge on date
    merged = pd.merge(co1_df, co2_df, on="date", suffixes=("_co1", "_co2"))

    # Compute spread, volume ratio, OI ratio
    merged["spread"] = merged["price_co1"] - merged["price_co2"]
    merged["volume_ratio"] = merged["volume_co1"] / merged["volume_co2"].replace(0, np.nan)
    merged["oi_ratio"] = merged["open_interest_co1"] / merged["open_interest_co2"].replace(0, np.nan)
    merged["total_volume"] = merged["volume_co1"].fillna(0) + merged["volume_co2"].fillna(0)
    merged["total_oi"] = merged["open_interest_co1"].fillna(0) + merged["open_interest_co2"].fillna(0)

    # Volume and OI changes
    merged["vol_co1_chg"] = merged["volume_co1"].pct_change() * 100
    merged["vol_co2_chg"] = merged["volume_co2"].pct_change() * 100
    merged["oi_co1_chg"] = merged["open_interest_co1"].pct_change() * 100
    merged["oi_co2_chg"] = merged["open_interest_co2"].pct_change() * 100

    # Recent data (last 30 rows)
    recent = merged.tail(30)

    timeseries = []
    for _, row in merged.iterrows():
        timeseries.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "co1_price": round(float(row["price_co1"]), 2) if pd.notna(row["price_co1"]) else None,
            "co2_price": round(float(row["price_co2"]), 2) if pd.notna(row["price_co2"]) else None,
            "spread": round(float(row["spread"]), 2) if pd.notna(row["spread"]) else None,
            "co1_volume": round(float(row["volume_co1"]), 0) if pd.notna(row["volume_co1"]) else None,
            "co2_volume": round(float(row["volume_co2"]), 0) if pd.notna(row["volume_co2"]) else None,
            "co1_oi": round(float(row["open_interest_co1"]), 0) if pd.notna(row["open_interest_co1"]) else None,
            "co2_oi": round(float(row["open_interest_co2"]), 0) if pd.notna(row["open_interest_co2"]) else None,
            "volume_ratio": round(float(row["volume_ratio"]), 2) if pd.notna(row["volume_ratio"]) else None,
            "oi_ratio": round(float(row["oi_ratio"]), 2) if pd.notna(row["oi_ratio"]) else None,
        })

    # Latest values
    latest = recent.iloc[-1] if len(recent) > 0 else None
    recent_5d = recent.tail(5)

    # OI trend analysis - is OI shifting from CO1 to CO2?
    oi_shift = None
    if len(recent) >= 10:
        co1_oi_trend = recent["open_interest_co1"].dropna()
        co2_oi_trend = recent["open_interest_co2"].dropna()
        if len(co1_oi_trend) >= 5 and len(co2_oi_trend) >= 5:
            co1_declining = co1_oi_trend.iloc[-1] < co1_oi_trend.iloc[-5]
            co2_rising = co2_oi_trend.iloc[-1] > co2_oi_trend.iloc[-5]
            oi_shift = "Roll Active" if co1_declining and co2_rising else "Roll Incomplete"

    # Volume trend - volume moving to CO2?
    vol_shift = None
    if len(recent_5d) >= 3:
        recent_vr = recent_5d["volume_ratio"].dropna()
        if len(recent_vr) >= 2:
            vol_shift = "CO2 Dominant" if recent_vr.iloc[-1] < 1.0 else "CO1 Still Dominant"

    summary = {}
    if latest is not None:
        summary = {
            "latest_date": latest["date"].strftime("%Y-%m-%d"),
            "co1_price": round(float(latest["price_co1"]), 2) if pd.notna(latest["price_co1"]) else None,
            "co2_price": round(float(latest["price_co2"]), 2) if pd.notna(latest["price_co2"]) else None,
            "spread": round(float(latest["spread"]), 2) if pd.notna(latest["spread"]) else None,
            "co1_volume": round(float(latest["volume_co1"]), 0) if pd.notna(latest["volume_co1"]) else None,
            "co2_volume": round(float(latest["volume_co2"]), 0) if pd.notna(latest["volume_co2"]) else None,
            "co1_oi": round(float(latest["open_interest_co1"]), 0) if pd.notna(latest["open_interest_co1"]) else None,
            "co2_oi": round(float(latest["open_interest_co2"]), 0) if pd.notna(latest["open_interest_co2"]) else None,
            "oi_shift": oi_shift,
            "vol_shift": vol_shift,
        }

    return {
        "timeseries": timeseries,
        "summary": summary,
    }


def _generate_trading_analysis():
    """
    Combine COT positioning, Money Positioning decomposition, and CO1/CO2
    contract data to generate a comprehensive trading analysis.
    """
    mp = _compute_money_positioning()
    ca = _compute_contract_analysis()

    analysis_points = []
    verdict = "NEUTRAL"
    confidence = 50

    # --- Money Positioning Analysis ---
    if mp and mp.get("summary"):
        ms = mp["summary"]
        fast = ms.get("fast_component")
        prev_fast = ms.get("prev_fast")
        pct = ms.get("net_percentile")
        weekly_chg = ms.get("weekly_change")
        monthly_chg = ms.get("monthly_change")

        if fast is not None:
            if fast > 1.0:
                analysis_points.append(f"Managed Money fast-component z-score at {fast:.2f} → strong CTA bullish positioning, but approaching overextension (reaction function attenuates above ~1.5σ)")
            elif fast > 0.3:
                analysis_points.append(f"Managed Money fast-component z-score at {fast:.2f} → moderate CTA bullish bias, room to add")
            elif fast < -1.0:
                analysis_points.append(f"Managed Money fast-component z-score at {fast:.2f} → strong CTA bearish positioning, potential for short squeeze if trends reverse")
            elif fast < -0.3:
                analysis_points.append(f"Managed Money fast-component z-score at {fast:.2f} → moderate CTA bearish tilt")
            else:
                analysis_points.append(f"Managed Money fast-component z-score at {fast:.2f} → CTAs near neutral, low directional conviction")

        if fast is not None and prev_fast is not None:
            direction = "building longs" if fast > prev_fast else "reducing longs/adding shorts"
            analysis_points.append(f"Week-over-week CTA trend: {direction} (fast component {prev_fast:.2f} → {fast:.2f})")

        if pct is not None:
            if pct > 80:
                analysis_points.append(f"Net position at {pct:.0f}th percentile historically → crowded long, limited dry powder for further buying")
            elif pct < 20:
                analysis_points.append(f"Net position at {pct:.0f}th percentile historically → light positioning, significant dry powder for buying")
            else:
                analysis_points.append(f"Net position at {pct:.0f}th percentile historically → mid-range positioning")

        if weekly_chg is not None:
            analysis_points.append(f"Weekly position change: {weekly_chg:+,} contracts")
        if monthly_chg is not None:
            analysis_points.append(f"4-week position change: {monthly_chg:+,} contracts")

    # --- All Category Positioning ---
    if "categories" in cot_data:
        cats = cot_data["categories"]
        for cat_name in ["Producers", "Swap Dealers"]:
            if cat_name in cats:
                cat_rows = cats[cat_name]["data"]
                if cat_rows:
                    latest = cat_rows[0]
                    net = latest.get("Net", latest.get("net", 0))
                    if net is not None:
                        analysis_points.append(f"{cat_name} net: {int(net):+,} contracts")

    # --- CO1/CO2 Contract Analysis ---
    if ca and ca.get("summary"):
        cs = ca["summary"]
        spread = cs.get("spread")
        oi_shift = cs.get("oi_shift")
        vol_shift = cs.get("vol_shift")
        co1_vol = cs.get("co1_volume")
        co2_vol = cs.get("co2_volume")
        co1_oi = cs.get("co1_oi")
        co2_oi = cs.get("co2_oi")

        if spread is not None:
            if spread > 0:
                analysis_points.append(f"CO1-CO2 spread: +${spread:.2f} (backwardation) → near-term supply tightness")
            else:
                analysis_points.append(f"CO1-CO2 spread: ${spread:.2f} (contango) → near-term oversupply signal")

        analysis_points.append(f"CONTRACT ROLL DYNAMICS: CO1 is expiring → CO2 becomes the new prompt month. Brent prompts expire at end of each month.")

        if oi_shift:
            analysis_points.append(f"Open Interest shift: {oi_shift} — CO1 OI: {int(co1_oi):,} | CO2 OI: {int(co2_oi):,}" if co1_oi and co2_oi else f"Open Interest shift: {oi_shift}")

        if vol_shift:
            analysis_points.append(f"Volume shift: {vol_shift} — CO1 Vol: {int(co1_vol):,} | CO2 Vol: {int(co2_vol):,}" if co1_vol and co2_vol else f"Volume shift: {vol_shift}")

        if co2_vol and co1_vol and co2_vol > co1_vol:
            analysis_points.append("Volume has already migrated to CO2 → roll is well underway, CO2 is the actionable contract")
        elif co1_vol and co2_vol:
            analysis_points.append("CO1 still showing higher volume → late rollers still active, watch for final squeeze")

        if co2_oi and co1_oi:
            if co2_oi > co1_oi * 1.5:
                analysis_points.append(f"CO2 OI ({int(co2_oi):,}) significantly exceeds CO1 OI ({int(co1_oi):,}) → position build-up in new prompt month")

    # --- Combined Verdict ---
    bull_signals = 0
    bear_signals = 0

    if mp and mp.get("summary"):
        fast = mp["summary"].get("fast_component")
        if fast is not None:
            if fast > 0.3:
                bull_signals += 2
            elif fast < -0.3:
                bear_signals += 2
            if mp["summary"].get("weekly_change") and mp["summary"]["weekly_change"] > 0:
                bull_signals += 1
            elif mp["summary"].get("weekly_change") and mp["summary"]["weekly_change"] < 0:
                bear_signals += 1

    if ca and ca.get("summary"):
        spread = ca["summary"].get("spread")
        if spread and spread > 0:
            bull_signals += 1
        elif spread and spread < 0:
            bear_signals += 1

    total = bull_signals + bear_signals
    if total > 0:
        if bull_signals > bear_signals:
            verdict = "BULLISH"
            confidence = min(85, 50 + (bull_signals - bear_signals) * 10)
        elif bear_signals > bull_signals:
            verdict = "BEARISH"
            confidence = min(85, 50 + (bear_signals - bull_signals) * 10)

    # Final note about contract roll
    analysis_points.append(f"\n**TRADING RECOMMENDATION ({verdict}, {confidence}% confidence):**")
    if verdict == "BULLISH":
        analysis_points.append("Managed Money CTAs are positioned long and/or building. With CO1 expiring, execute on CO2 (new prompt). Watch for post-roll momentum continuation.")
    elif verdict == "BEARISH":
        analysis_points.append("Managed Money CTAs are reducing/short. With CO1 expiring, CO2 inherits bearish momentum. Consider short or wait for clearer reversal signals.")
    else:
        analysis_points.append("Mixed signals. With CO1 expiring, CO2 becomes the reference. Wait for CTA positioning to break out of neutral zone before committing.")

    return {
        "verdict": verdict,
        "confidence": confidence,
        "analysis_points": analysis_points,
        "money_positioning": mp,
        "contract_analysis": ca,
        "generated_at": datetime.utcnow().isoformat(),
    }


@app.get("/api/money_positioning")
async def get_money_positioning():
    """Get OIES Insight 177 Money Positioning analysis."""
    result = _compute_money_positioning()
    if not result:
        raise HTTPException(status_code=404, detail="No Managed Money data available. Upload COT data first.")
    return result


@app.get("/api/contract_analysis")
async def get_contract_analysis():
    """Get CO1/CO2 contract analysis with volume and open interest."""
    result = _compute_contract_analysis()
    if not result:
        raise HTTPException(status_code=404, detail="No CO1/CO2 data available. Upload COTnew.xlsx.")
    return result


@app.get("/api/trading_analysis")
async def get_trading_analysis():
    """Get combined trading analysis: COT + Money Positioning + CO1/CO2."""
    return _generate_trading_analysis()


@app.get("/api/co_prices")
async def get_co_prices():
    """Get raw CO1/CO2 price, volume, and OI data."""
    if not co_price_data:
        raise HTTPException(status_code=404, detail="No CO1/CO2 data loaded")
    return co_price_data


# ═══════════════════════════════════════════════════════════════════════════════
# EIA GASOLINE BALANCES — Monthly S&D from /petroleum/sum/snd/ (Live API v2)
# Products: EPM0C, EPM0F, EPM0R, EPOBG, EPOBGC0, EPOBGR0, EPOBV, EPP2
# ═══════════════════════════════════════════════════════════════════════════════

GB_AREA_MAP = {
    "US": {"name": "U.S.", "duo": "NUS"},
    "PADD1": {"name": "East Coast (PADD 1)", "duo": "R10"},
    "PADD2": {"name": "Midwest (PADD 2)", "duo": "R20"},
    "PADD3": {"name": "Gulf Coast (PADD 3)", "duo": "R30"},
    "PADD4": {"name": "Rocky Mountain (PADD 4)", "duo": "R40"},
    "PADD5": {"name": "West Coast (PADD 5)", "duo": "R50"},
}

GB_PRODUCTS = [
    ("EPM0F", "Finished Motor Gasoline"),
    ("EPM0C", "Conventional Motor Gasoline"),
    ("EPM0R", "Reformulated Motor Gasoline"),
    ("EPOBG", "Gasoline Blending Components"),
    ("EPOBGC0", "Conventional Blend Components"),
    ("EPOBGR0", "Reformulated Blend Components"),
    ("EPOBV", "Aviation Gasoline Blend Comp."),
    ("EPP2", "Finished Petroleum Products"),
]

GB_PROCESS_NAMES = {
    "YPR": "Refinery/Blender Production",
    "YIR": "Refinery/Blender Net Input",
    "YNP": "Renewable/Oxygenate Production",
    "VPP": "Product Supplied (Demand)",
    "VUA": "Supply Adjustment",
    "SCG": "Stock Change",
    "SAE": "Ending Stocks",
}

def _fetch_eia_v2(url: str) -> dict:
    import urllib.request
    import json as _json
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "CrudeOilPlatform/1.0")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return _json.loads(resp.read().decode())


def _fetch_all_gb_pages(api_key: str, duo: str, start_ym: str, end_ym: str) -> list:
    """Fetch all pages from the monthly S&D endpoint for 8 products."""
    products = [p[0] for p in GB_PRODUCTS]
    prod_param = "".join(f"&facets[product][]={p}" for p in products)
    all_records: list = []
    offset = 0
    page_size = 5000
    while True:
        url = (
            f"https://api.eia.gov/v2/petroleum/sum/snd/data/"
            f"?api_key={api_key}&frequency=monthly&data[0]=value"
            f"&facets[duoarea][]={duo}{prod_param}"
            f"&start={start_ym}&end={end_ym}"
            f"&sort[0][column]=period&sort[0][direction]=desc"
            f"&offset={offset}&length={page_size}"
        )
        raw = _fetch_eia_v2(url)
        data = raw.get("response", {}).get("data", [])
        all_records.extend(data)
        if len(data) < page_size:
            break
        offset += page_size
    return all_records


@app.get("/api/eia_gasoline_balances")
async def get_eia_gasoline_balances(
    area: str = Query("US", description="Region: US, PADD1-5"),
    start_year: int = Query(2015, description="Start year"),
    end_year: int = Query(2026, description="End year"),
):
    """Monthly gasoline S&D balance from EIA /petroleum/sum/snd/ with multi-year overlay."""
    api_key = os.environ.get("EIA_API_KEY", "7SzAygceNwO58RBgwVgV7dkk163Bk73xzFF36lq6")
    if not api_key:
        raise HTTPException(status_code=500, detail="EIA_API_KEY not set")
    if area not in GB_AREA_MAP:
        raise HTTPException(status_code=400, detail=f"Invalid area: {list(GB_AREA_MAP.keys())}")

    duo = GB_AREA_MAP[area]["duo"]
    start_ym = f"{start_year}-01"
    end_ym = f"{end_year}-12"

    try:
        all_records = _fetch_all_gb_pages(api_key, duo, start_ym, end_ym)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"EIA API error: {e}")

    from collections import defaultdict

    # Index: (product, process) -> sorted list of {period, value, units, series}
    series_map: dict = defaultdict(list)
    for rec in all_records:
        prod = rec.get("product", "")
        proc = rec.get("process", "")
        val = rec.get("value")
        units = rec.get("units", "")
        period = rec.get("period", "")
        series_map[(prod, proc, units)].append({
            "period": period,
            "value": float(val) if val is not None else None,
            "series": rec.get("series", ""),
            "desc": rec.get("series-description", ""),
        })

    # Sort each list chronologically
    for key in series_map:
        series_map[key].sort(key=lambda x: x["period"])

    # Build S&D table: for each product, list available processes with stats
    snd_table = []
    for prod_code, prod_name in GB_PRODUCTS:
        row = {
            "product": prod_code,
            "product_name": prod_name,
            "processes": {},
        }
        for proc_code, proc_name in GB_PROCESS_NAMES.items():
            # Prefer MBBL/D for flow rates, MBBL for stocks
            prefer_unit = "MBBL" if proc_code == "SAE" else "MBBL/D"
            key = (prod_code, proc_code, prefer_unit)
            entries = series_map.get(key, [])
            if not entries:
                # Try the other unit
                alt_unit = "MBBL/D" if prefer_unit == "MBBL" else "MBBL"
                key = (prod_code, proc_code, alt_unit)
                entries = series_map.get(key, [])
            if not entries:
                continue
            vals = [e["value"] for e in entries]
            clean = [v for v in vals if v is not None]
            if len(clean) < 2:
                continue
            latest = clean[-1]
            prev = clean[-2]
            chg = latest - prev
            n60 = min(len(clean), 60)  # ~5 years monthly
            avg5 = float(np.mean(clean[-n60:]))
            n12 = min(len(clean), 12)
            row["processes"][proc_code] = {
                "name": proc_name,
                "series_id": entries[-1]["series"],
                "units": key[2],
                "latest": round(latest, 1),
                "previous": round(prev, 1),
                "mom_change": round(chg, 1),
                "pct_change": round(chg / prev * 100, 2) if prev != 0 else 0,
                "avg_5y": round(avg5, 1),
                "vs_avg": round(latest - avg5, 1),
                "min_12m": round(min(clean[-n12:]), 1),
                "max_12m": round(max(clean[-n12:]), 1),
            }
        if row["processes"]:
            snd_table.append(row)

    # Build multi-year overlay data for seasonal charts
    # For each product+process, group values by year and month
    MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    seasonal_overlay: dict = {}
    for prod_code, prod_name in GB_PRODUCTS:
        for proc_code, proc_name in GB_PROCESS_NAMES.items():
            prefer_unit = "MBBL" if proc_code == "SAE" else "MBBL/D"
            key = (prod_code, proc_code, prefer_unit)
            entries = series_map.get(key, [])
            if not entries:
                alt_unit = "MBBL/D" if prefer_unit == "MBBL" else "MBBL"
                key = (prod_code, proc_code, alt_unit)
                entries = series_map.get(key, [])
            if len(entries) < 12:
                continue
            # Group by year
            year_data: dict = defaultdict(lambda: [None] * 12)
            for e in entries:
                try:
                    yr = int(e["period"][:4])
                    mo = int(e["period"][5:7])
                    if 1 <= mo <= 12:
                        year_data[yr][mo - 1] = e["value"]
                except (ValueError, IndexError):
                    pass
            # Only include years with at least 6 months of data
            filtered = {}
            for yr, vals in sorted(year_data.items()):
                non_null = sum(1 for v in vals if v is not None)
                if non_null >= 6:
                    filtered[str(yr)] = [round(v, 1) if v is not None else None for v in vals]
            if len(filtered) >= 2:
                overlay_key = f"{prod_code}_{proc_code}"
                seasonal_overlay[overlay_key] = {
                    "product": prod_code,
                    "product_name": prod_name,
                    "process": proc_code,
                    "process_name": proc_name,
                    "units": key[2],
                    "months": MONTH_NAMES,
                    "years": filtered,
                }

    # Build time-series for line charts (full history)
    chart_series: dict = {}
    for prod_code, prod_name in GB_PRODUCTS:
        for proc_code, proc_name in GB_PROCESS_NAMES.items():
            prefer_unit = "MBBL" if proc_code == "SAE" else "MBBL/D"
            key = (prod_code, proc_code, prefer_unit)
            entries = series_map.get(key, [])
            if not entries:
                alt_unit = "MBBL/D" if prefer_unit == "MBBL" else "MBBL"
                key = (prod_code, proc_code, alt_unit)
                entries = series_map.get(key, [])
            if len(entries) < 2:
                continue
            cs_key = f"{prod_code}_{proc_code}"
            chart_series[cs_key] = {
                "product": prod_code,
                "product_name": prod_name,
                "process": proc_code,
                "process_name": proc_name,
                "units": key[2],
                "dates": [e["period"] for e in entries],
                "values": [round(e["value"], 1) if e["value"] is not None else None for e in entries],
            }

    # Derive available year range from data
    all_years = set()
    for entries_list in series_map.values():
        for e in entries_list:
            try:
                all_years.add(int(e["period"][:4]))
            except (ValueError, IndexError):
                pass

    return {
        "area": area,
        "area_name": GB_AREA_MAP[area]["name"],
        "start_year": start_year,
        "end_year": end_year,
        "snd_table": snd_table,
        "seasonal_overlay": seasonal_overlay,
        "chart_series": chart_series,
        "available_years": sorted(all_years),
        "available_areas": {k: v["name"] for k, v in GB_AREA_MAP.items()},
        "products": [{"code": p[0], "name": p[1]} for p in GB_PRODUCTS],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EIA GASOLINE MONTHLY BALANCE TABLE — Spreadsheet-style balance (like crude example)
# ═══════════════════════════════════════════════════════════════════════════════

GB_MONTHLY_STOCK_ROWS = [
    {"key": "stocks_finished", "label": "Finished Motor Gasoline Stocks", "src": "snd", "product": "EPM0F", "process": "SAE", "unit": "MBBL"},
    {"key": "stocks_blending", "label": "Blending Components Stocks", "src": "snd", "product": "EPOBG", "process": "SAE", "unit": "MBBL"},
    {"key": "stocks_ethanol", "label": "Fuel Ethanol Stocks", "src": "snd", "product": "EPOOXE", "process": "SAE", "unit": "MBBL"},
]


def _fetch_eia_gasoline_area(api_key: str, duo: str, start_ym: str, end_ym: str) -> dict:
    """Fetch monthly gasoline data for one area from EIA endpoints.
    Returns {(source, product, process, units): {period: value}}."""
    from collections import defaultdict
    result: dict = defaultdict(dict)

    # 1) S&D endpoint — production, stock change, product supplied, etc.
    snd_products = ["EPM0F", "EPOBG", "EPOOXE"]
    prod_param = "".join(f"&facets[product][]={p}" for p in snd_products)
    offset = 0
    while True:
        url = (
            f"https://api.eia.gov/v2/petroleum/sum/snd/data/"
            f"?api_key={api_key}&frequency=monthly&data[0]=value"
            f"&facets[duoarea][]={duo}{prod_param}"
            f"&start={start_ym}&end={end_ym}"
            f"&sort[0][column]=period&sort[0][direction]=asc"
            f"&offset={offset}&length=5000"
        )
        raw = _fetch_eia_v2(url)
        data = raw.get("response", {}).get("data", [])
        for rec in data:
            prod = rec.get("product", "")
            proc = rec.get("process", "")
            units = rec.get("units", "")
            val = rec.get("value")
            period = rec.get("period", "")
            if val is None:
                continue
            try:
                fval = float(val)
            except (ValueError, TypeError):
                continue
            result[("snd", prod, proc, units)][period] = fval
        if len(data) < 5000:
            break
        offset += 5000

    # 2) Imports endpoint (finished + blending components)
    imp_duo = duo + "-Z00" if "-" not in duo else duo
    for imp_prod in ["EPM0F", "EPOBG"]:
        url = (
            f"https://api.eia.gov/v2/petroleum/move/imp/data/"
            f"?api_key={api_key}&frequency=monthly&data[0]=value"
            f"&facets[duoarea][]={imp_duo}&facets[product][]={imp_prod}"
            f"&start={start_ym}&end={end_ym}"
            f"&sort[0][column]=period&sort[0][direction]=asc"
            f"&length=5000"
        )
        try:
            raw = _fetch_eia_v2(url)
            for rec in raw.get("response", {}).get("data", []):
                units = rec.get("units", "")
                val = rec.get("value")
                period = rec.get("period", "")
                if val is None:
                    continue
                try:
                    fval = float(val)
                except (ValueError, TypeError):
                    continue
                result[("imp", imp_prod, "IM0", units)][period] = fval
        except Exception:
            pass

    # 3) Exports endpoint (finished + blending components)
    exp_duo = duo + "-Z00" if "-" not in duo else duo
    for exp_prod in ["EPM0F", "EPOBG"]:
        url = (
            f"https://api.eia.gov/v2/petroleum/move/exp/data/"
            f"?api_key={api_key}&frequency=monthly&data[0]=value"
            f"&facets[duoarea][]={exp_duo}&facets[product][]={exp_prod}"
            f"&start={start_ym}&end={end_ym}"
            f"&sort[0][column]=period&sort[0][direction]=asc"
            f"&length=5000"
        )
        try:
            raw = _fetch_eia_v2(url)
            for rec in raw.get("response", {}).get("data", []):
                units = rec.get("units", "")
                val = rec.get("value")
                period = rec.get("period", "")
                if val is None:
                    continue
                try:
                    fval = float(val)
                except (ValueError, TypeError):
                    continue
                result[("exp", exp_prod, "EEX", units)][period] = fval
        except Exception:
            pass

    return dict(result)


def _build_gasoline_balance(raw: dict, periods: list, area_name: str) -> dict:
    """Build gasoline balance from raw EIA data.
    Uses finished motor gasoline (EPM0F) for the primary balance:
      Supply = Production + Imports + Adjustment
      Demand = Product Supplied + Exports + Stock Change
    Then adds blending component & ethanol supplementary rows."""

    def _gs(src: str, prod: str, proc: str, unit: str = "MBBL/D") -> dict:
        return raw.get((src, prod, proc, unit), {})

    def _make_row(key: str, label: str, series: dict, **kwargs) -> dict:
        return {"key": key, "label": label, "values": {p: series.get(p) for p in periods}, "unit": "kb/d", **kwargs}

    # --- PRIMARY BALANCE (Finished Motor Gasoline — EPM0F) ---
    production = _gs("snd", "EPM0F", "YPR")
    imports_fin = _gs("imp", "EPM0F", "IM0")
    adjustment = _gs("snd", "EPM0F", "VUA")
    exports_fin = _gs("exp", "EPM0F", "EEX")
    demand_ps = _gs("snd", "EPM0F", "VPP")
    scg_fin = _gs("snd", "EPM0F", "SCG")

    balance_rows = [
        _make_row("production", "Refinery & Blender Net Production", production),
        _make_row("imports_finished", "Imports — Finished Gasoline", imports_fin),
        _make_row("adjustment", "Supply Adjustment", adjustment),
    ]

    # Total Supply = Production + Imports + Adjustment
    total_supply = {}
    for p in periods:
        vals = [production.get(p), imports_fin.get(p), adjustment.get(p)]
        clean = [v for v in vals if v is not None]
        total_supply[p] = round(sum(clean), 1) if clean else None
    balance_rows.append(_make_row("total_supply", "TOTAL SUPPLY", total_supply, is_total=True))

    # Demand-side rows
    balance_rows.append(_make_row("exports_finished", "Exports — Finished Gasoline", exports_fin))
    balance_rows.append(_make_row("demand", "Product Supplied (Demand)", demand_ps))
    balance_rows.append(_make_row("stock_change", "Stock Change (Finished)", scg_fin))

    # Total Demand = Exports + Product Supplied + Stock Change
    total_demand = {}
    for p in periods:
        vals = [exports_fin.get(p), demand_ps.get(p), scg_fin.get(p)]
        clean = [v for v in vals if v is not None]
        total_demand[p] = round(sum(clean), 1) if clean else None
    balance_rows.append(_make_row("total_demand", "TOTAL DISPOSITION", total_demand, is_total=True))

    # Balance = Supply - Disposition (should be ~0)
    bal = {}
    for p in periods:
        s, d = total_supply.get(p), total_demand.get(p)
        bal[p] = round(s - d, 1) if s is not None and d is not None else None
    balance_rows.append(_make_row("balance", "BALANCE (residual)", bal, is_balance=True))

    # --- SUPPLEMENTARY: Blending Components ---
    imports_bc = _gs("imp", "EPOBG", "IM0")
    exports_bc = _gs("exp", "EPOBG", "EEX")
    scg_bc = _gs("snd", "EPOBG", "SCG")
    ethanol_prod = _gs("snd", "EPOOXE", "YNP")
    scg_eth = _gs("snd", "EPOOXE", "SCG")

    supp_rows = [
        _make_row("imports_blending", "Blending Components — Imports", imports_bc, is_supplementary=True),
        _make_row("exports_blending", "Blending Components — Exports", exports_bc, is_supplementary=True),
        _make_row("scg_blending", "Blending Components — Stock Change", scg_bc, is_supplementary=True),
        _make_row("ethanol_prod", "Fuel Ethanol — Net Production", ethanol_prod, is_supplementary=True),
        _make_row("scg_ethanol", "Fuel Ethanol — Stock Change", scg_eth, is_supplementary=True),
    ]

    # Stock levels (MBBL → mmb)
    stock_rows = []
    for row_def in GB_MONTHLY_STOCK_ROWS:
        series = _gs("snd", row_def["product"], row_def["process"], row_def.get("unit", "MBBL"))
        stock_rows.append({
            "key": row_def["key"], "label": row_def["label"],
            "values": {p: series.get(p) for p in periods}, "unit": "mmb",
        })

    return {
        "balance_rows": balance_rows,
        "supplementary_rows": supp_rows,
        "stock_rows": stock_rows,
    }


def _add_projections(result: dict, periods: list, proj_months: list) -> dict:
    """Add seasonal-average projections for future months.
    proj_months: list of 'YYYY-MM' strings to project.
    Uses average of same calendar month across available years."""
    from collections import defaultdict

    all_row_lists = ["balance_rows", "supplementary_rows", "stock_rows"]
    extended_periods = sorted(set(periods) | set(proj_months))

    for list_key in all_row_lists:
        for row in result.get(list_key, []):
            if row.get("is_total") or row.get("is_balance"):
                continue
            vals = row["values"]
            # Group values by calendar month (01-12)
            by_month: dict = defaultdict(list)
            for p, v in vals.items():
                if v is not None:
                    mm = p.split("-")[1]
                    by_month[mm].append(v)
            # Compute average for each projection month
            for pm in proj_months:
                mm = pm.split("-")[1]
                hist = by_month.get(mm, [])
                if hist:
                    vals[pm] = round(sum(hist) / len(hist), 1)

    # Recompute totals and balance for projected months
    for list_key in ["balance_rows"]:
        rows = result.get(list_key, [])
        supply_keys = ["production", "imports_finished", "adjustment"]
        demand_keys = ["exports_finished", "demand", "stock_change"]

        total_supply_row = next((r for r in rows if r["key"] == "total_supply"), None)
        total_demand_row = next((r for r in rows if r["key"] == "total_demand"), None)
        balance_row = next((r for r in rows if r["key"] == "balance"), None)

        for pm in proj_months:
            # Total Supply
            if total_supply_row:
                s_vals = [next((r for r in rows if r["key"] == k), None) for k in supply_keys]
                s_clean = [r["values"].get(pm) for r in s_vals if r and r["values"].get(pm) is not None]
                total_supply_row["values"][pm] = round(sum(s_clean), 1) if s_clean else None
            # Total Demand
            if total_demand_row:
                d_vals = [next((r for r in rows if r["key"] == k), None) for k in demand_keys]
                d_clean = [r["values"].get(pm) for r in d_vals if r and r["values"].get(pm) is not None]
                total_demand_row["values"][pm] = round(sum(d_clean), 1) if d_clean else None
            # Balance
            if balance_row and total_supply_row and total_demand_row:
                s = total_supply_row["values"].get(pm)
                d = total_demand_row["values"].get(pm)
                balance_row["values"][pm] = round(s - d, 1) if s is not None and d is not None else None

    result["projected_periods"] = proj_months
    return result


@app.get("/api/eia_gasoline_monthly")
async def get_eia_gasoline_monthly(
    start_year: int = Query(2024, description="Start year"),
    end_year: int = Query(2026, description="End year"),
):
    """Monthly gasoline balance table — US Total + all 5 PADDs with projections."""
    api_key = os.environ.get("EIA_API_KEY", "7SzAygceNwO58RBgwVgV7dkk163Bk73xzFF36lq6")
    if not api_key:
        raise HTTPException(status_code=500, detail="EIA_API_KEY not set")

    # Fetch historical data going back further for better seasonal averages
    hist_start = max(2020, start_year - 3)
    start_ym = f"{hist_start}-01"
    end_ym = f"{end_year}-12"

    areas = [
        ("US", "NUS", "U.S. Total"),
        ("PADD1", "R10", "East Coast (PADD 1)"),
        ("PADD2", "R20", "Midwest (PADD 2)"),
        ("PADD3", "R30", "Gulf Coast (PADD 3)"),
        ("PADD4", "R40", "Rocky Mountain (PADD 4)"),
        ("PADD5", "R50", "West Coast (PADD 5)"),
    ]

    sections = []
    for area_code, duo, area_name in areas:
        try:
            raw = _fetch_eia_gasoline_area(api_key, duo, start_ym, end_ym)
        except Exception as e:
            sections.append({"area": area_code, "area_name": area_name, "error": str(e)})
            continue

        # Collect periods
        all_periods: set = set()
        for series_data in raw.values():
            all_periods.update(series_data.keys())
        periods = sorted(all_periods)

        result = _build_gasoline_balance(raw, periods, area_name)

        # Determine projection months: find last actual month, project forward
        actual_periods = [p for p in periods if p >= f"{start_year}-01"]
        if actual_periods:
            last_actual = actual_periods[-1]
            ly, lm = int(last_actual.split("-")[0]), int(last_actual.split("-")[1])
            proj_months = []
            # Project through Sep of the same year (or next if we're past Sep)
            proj_end_month = 9  # September
            proj_end_year = ly if lm < 10 else ly + 1
            cy, cm = ly, lm + 1
            if cm > 12:
                cm = 1
                cy += 1
            while (cy < proj_end_year) or (cy == proj_end_year and cm <= proj_end_month):
                proj_months.append(f"{cy}-{cm:02d}")
                cm += 1
                if cm > 12:
                    cm = 1
                    cy += 1
            if proj_months:
                result = _add_projections(result, periods, proj_months)
                periods = sorted(set(periods) | set(proj_months))

        # Filter to only show from start_year onward in the response
        display_periods = [p for p in periods if p >= f"{start_year}-01"]

        result["area"] = area_code
        result["area_name"] = area_name
        result["periods"] = display_periods
        sections.append(result)

    return {
        "start_year": start_year,
        "end_year": end_year,
        "sections": sections,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EIA GASOLINE STOCKS — Live API v2 (Weekly Petroleum Stocks)
# ═══════════════════════════════════════════════════════════════════════════════

EIA_GAS_STOCKS_PRODUCTS = [
    "EPM0", "EPM0C", "EPM0CA", "EPM0CAG5S", "EPM0CO",
    "EPM0F", "EPM0R", "EPM0RA",
    "EPOBG", "EPOBGCC", "EPOBGCG", "EPOBGCO",
    "EPOBGRG", "EPOBGRR", "EPOBGRRA", "EPOBGRRE",
    "EPOOXE",
]

EIA_GAS_PRODUCT_NAMES = {
    "EPM0": "Total Motor Gasoline",
    "EPM0C": "Conventional Motor Gasoline",
    "EPM0CA": "Conventional Areas",
    "EPM0CAG5S": "Conventional CBOB (RFG Areas)",
    "EPM0CO": "Conventional Other",
    "EPM0F": "Finished Motor Gasoline",
    "EPM0R": "Reformulated Motor Gasoline",
    "EPM0RA": "Reformulated Areas",
    "EPOBG": "Total Blending Components",
    "EPOBGCC": "Blending Components CBOB",
    "EPOBGCG": "Blending Components GTAB",
    "EPOBGCO": "Blending Components Other",
    "EPOBGRG": "Reformulated Blending RBOB",
    "EPOBGRR": "Reformulated Blending",
    "EPOBGRRA": "Reformulated Blending Areas",
    "EPOBGRRE": "Reformulated Blending RE",
    "EPOOXE": "Fuel Ethanol",
}

eia_gasoline_cache: dict = {}


@app.get("/api/eia_gasoline_stocks")
async def get_eia_gasoline_stocks(
    start: str = Query("2020-01-01", description="Start date (YYYY-MM-DD)"),
    end: str = Query("2026-12-31", description="End date (YYYY-MM-DD)"),
    length: int = Query(5000, description="Max records"),
):
    """Fetch weekly gasoline stocks from EIA API v2."""
    import urllib.request
    import json as json_mod

    api_key = os.environ.get("EIA_API_KEY", "7SzAygceNwO58RBgwVgV7dkk163Bk73xzFF36lq6")
    if not api_key:
        raise HTTPException(status_code=500, detail="EIA_API_KEY environment variable not set. Please configure your EIA API key.")

    # Build URL with all product facets
    base_url = "https://api.eia.gov/v2/petroleum/stoc/wstk/data/"
    params = f"?api_key={api_key}&frequency=weekly"
    params += "&data[0]=value"
    for p in EIA_GAS_STOCKS_PRODUCTS:
        params += f"&facets[product][]={p}"
    params += f"&start={start}&end={end}"
    params += "&sort[0][column]=period&sort[0][direction]=desc"
    params += f"&offset=0&length={length}"

    url = base_url + params

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "CrudeOilPlatform/1.0")
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json_mod.loads(resp.read().decode())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"EIA API error: {str(e)}")

    if "error" in raw:
        raise HTTPException(status_code=502, detail=f"EIA API: {raw['error'].get('message', str(raw['error']))}")

    response_data = raw.get("response", {})
    records = response_data.get("data", [])

    # Group by product + area
    by_product_area = {}
    for rec in records:
        prod = rec.get("product", "")
        area = rec.get("area-name", "U.S.")
        key = f"{prod}|{area}"
        if key not in by_product_area:
            by_product_area[key] = {
                "product_id": prod,
                "product_name": rec.get("product-name", EIA_GAS_PRODUCT_NAMES.get(prod, prod)),
                "area_name": area,
                "unit": rec.get("units", "Thousand Barrels"),
                "dates": [],
                "values": [],
            }
        val = rec.get("value")
        by_product_area[key]["dates"].append(rec.get("period", ""))
        by_product_area[key]["values"].append(float(val) if val is not None else None)

    # Reverse to chronological order
    for prod in by_product_area.values():
        prod["dates"].reverse()
        prod["values"].reverse()

    # Separate U.S. totals from PADD breakdowns
    us_products = {}
    padd_data = {}
    for key, pdata in by_product_area.items():
        pid = pdata["product_id"]
        area = pdata["area_name"]
        if area == "U.S.":
            us_products[pid] = pdata
        else:
            if pid not in padd_data:
                padd_data[pid] = {}
            padd_data[pid][area] = pdata

    # Compute summary stats for U.S. totals
    summary = {}
    for pid, pdata in us_products.items():
        vals = [v for v in pdata["values"] if v is not None]
        if len(vals) >= 2:
            latest = vals[-1]
            prev = vals[-2]
            change = latest - prev
            avg_5y = np.mean(vals[-260:]) if len(vals) >= 260 else np.mean(vals)
            diff_from_avg = latest - avg_5y
            summary[pid] = {
                "product_name": pdata["product_name"],
                "latest": round(latest, 1),
                "previous": round(prev, 1),
                "change": round(change, 1),
                "pct_change": round(change / prev * 100, 2) if prev != 0 else 0,
                "avg_5y": round(avg_5y, 1),
                "diff_from_avg": round(diff_from_avg, 1),
                "pct_diff_from_avg": round(diff_from_avg / avg_5y * 100, 2) if avg_5y != 0 else 0,
                "min_52w": round(min(vals[-52:]), 1) if len(vals) >= 52 else round(min(vals), 1),
                "max_52w": round(max(vals[-52:]), 1) if len(vals) >= 52 else round(max(vals), 1),
            }

    # Calculate seasonal pattern for Total Motor Gasoline (EPM0) - U.S. total
    seasonal = {}
    if "EPM0" in us_products:
        dates = us_products["EPM0"]["dates"]
        vals = us_products["EPM0"]["values"]
        from collections import defaultdict
        weekly_avg = defaultdict(list)
        for d, v in zip(dates, vals):
            if v is not None and d:
                try:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    week = dt.isocalendar()[1]
                    weekly_avg[week].append(v)
                except:
                    pass
        seasonal = {w: round(np.mean(vs), 1) for w, vs in sorted(weekly_avg.items())}

    # PADD breakdown for EPM0 (Total Gasoline)
    padd_breakdown = {}
    if "EPM0" in padd_data:
        for area, pdata in padd_data["EPM0"].items():
            vals = [v for v in pdata["values"] if v is not None]
            if vals:
                padd_breakdown[area] = {
                    "latest": round(vals[-1], 1),
                    "previous": round(vals[-2], 1) if len(vals) >= 2 else None,
                    "change": round(vals[-1] - vals[-2], 1) if len(vals) >= 2 else None,
                    "dates": pdata["dates"],
                    "values": pdata["values"],
                }

    return {
        "products": us_products,
        "padd_data": padd_breakdown,
        "summary": summary,
        "seasonal": seasonal,
        "product_names": EIA_GAS_PRODUCT_NAMES,
        "total_records": len(records),
        "latest_date": records[0].get("period") if records else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# JODI GASOLINE — Global Gasoline S&D from JODI World Database
# ═══════════════════════════════════════════════════════════════════════════════

JODI_COUNTRY_NAMES = {
    "AE": "UAE", "AL": "Albania", "AM": "Armenia", "AO": "Angola",
    "AR": "Argentina", "AT": "Austria", "AU": "Australia", "AZ": "Azerbaijan",
    "BB": "Barbados", "BD": "Bangladesh", "BE": "Belgium", "BG": "Bulgaria",
    "BH": "Bahrain", "BM": "Bermuda", "BN": "Brunei", "BO": "Bolivia",
    "BR": "Brazil", "BY": "Belarus", "BZ": "Belize", "CA": "Canada",
    "CH": "Switzerland", "CL": "Chile", "CN": "China", "CO": "Colombia",
    "CR": "Costa Rica", "CU": "Cuba", "CY": "Cyprus", "CZ": "Czechia",
    "DE": "Germany", "DK": "Denmark", "DO": "Dominican Rep.", "DZ": "Algeria",
    "EC": "Ecuador", "EE": "Estonia", "EG": "Egypt", "ES": "Spain",
    "FI": "Finland", "FR": "France", "GA": "Gabon", "GB": "United Kingdom",
    "GD": "Grenada", "GE": "Georgia", "GM": "Gambia", "GQ": "Eq. Guinea",
    "GR": "Greece", "GT": "Guatemala", "GY": "Guyana", "HK": "Hong Kong",
    "HN": "Honduras", "HR": "Croatia", "HT": "Haiti", "HU": "Hungary",
    "ID": "Indonesia", "IE": "Ireland", "IN": "India", "IQ": "Iraq",
    "IR": "Iran", "IS": "Iceland", "IT": "Italy", "JM": "Jamaica",
    "JP": "Japan", "KR": "South Korea", "KW": "Kuwait", "KZ": "Kazakhstan",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya",
    "MA": "Morocco", "MD": "Moldova", "MK": "North Macedonia", "MM": "Myanmar",
    "MT": "Malta", "MU": "Mauritius", "MX": "Mexico", "MY": "Malaysia",
    "NE": "Niger", "NG": "Nigeria", "NI": "Nicaragua", "NL": "Netherlands",
    "NO": "Norway", "NP": "Nepal", "NZ": "New Zealand", "OM": "Oman",
    "PA": "Panama", "PE": "Peru", "PG": "Papua New Guinea", "PH": "Philippines",
    "PL": "Poland", "PT": "Portugal", "PY": "Paraguay", "QA": "Qatar",
    "RO": "Romania", "RS": "Serbia", "RU": "Russia", "SA": "Saudi Arabia",
    "SD": "Sudan", "SE": "Sweden", "SG": "Singapore", "SI": "Slovenia",
    "SK": "Slovakia", "SR": "Suriname", "SV": "El Salvador", "SY": "Syria",
    "SZ": "Eswatini", "TH": "Thailand", "TJ": "Tajikistan", "TN": "Tunisia",
    "TR": "Turkey", "TT": "Trinidad & Tobago", "TW": "Taiwan", "UA": "Ukraine",
    "US": "United States", "UY": "Uruguay", "VE": "Venezuela", "VN": "Vietnam",
    "YE": "Yemen", "ZA": "South Africa",
}

JODI_REGIONS = {
    "R_EUROPE": {
        "name": "🌍 Europe",
        "countries": ["AT", "BE", "BG", "BY", "CH", "CY", "CZ", "DE", "DK",
                       "EE", "ES", "FI", "FR", "GB", "GR", "HR", "HU", "IE",
                       "IS", "IT", "LT", "LU", "LV", "MD", "MK", "MT", "NL",
                       "NO", "PL", "PT", "RO", "RS", "SE", "SI", "SK", "UA", "AL"],
    },
    "R_MIDDLE_EAST": {
        "name": "🌍 Middle East",
        "countries": ["AE", "BH", "IQ", "IR", "KW", "OM", "QA", "SA", "SY", "YE"],
    },
    "R_ASIA_PACIFIC": {
        "name": "🌏 Asia Pacific",
        "countries": ["AU", "BD", "BN", "CN", "HK", "ID", "IN", "JP", "KR",
                       "MM", "MY", "NP", "NZ", "PG", "PH", "SG", "TH", "TW", "VN"],
    },
    "R_NORTH_AMERICA": {
        "name": "🌎 North America",
        "countries": ["CA", "MX", "US"],
    },
    "R_LATIN_AMERICA": {
        "name": "🌎 Latin America & Caribbean",
        "countries": ["AR", "BB", "BM", "BO", "BR", "BZ", "CL", "CO", "CR",
                       "CU", "DO", "EC", "GD", "GT", "GY", "HN", "HT", "JM",
                       "NI", "PA", "PE", "PY", "SR", "SV", "TT", "UY", "VE"],
    },
    "R_AFRICA": {
        "name": "🌍 Africa",
        "countries": ["AO", "DZ", "EG", "GA", "GM", "GQ", "LY", "MA", "MU",
                       "NE", "NG", "SD", "SZ", "TN", "ZA"],
    },
    "R_FSU": {
        "name": "🌍 FSU / Central Asia",
        "countries": ["AM", "AZ", "GE", "KZ", "RU", "TJ"],
    },
    "R_TURKEY": {
        "name": "🌍 Turkey",
        "countries": ["TR"],
    },
}

JODI_FLOW_NAMES = {
    "REFGROUT": "Refinery Output",
    "TOTIMPSB": "Imports",
    "TOTEXPSB": "Exports",
    "TOTDEMO": "Demand",
    "CLOSTLV": "Closing Stocks",
    "STOCKCH": "Stock Change",
    "RECEIPTS": "Receipts",
    "PTRANSF": "Product Transfers",
    "IPTRANSF": "Interproduct Transfers",
    "STATDIFF": "Statistical Difference",
}

JODI_FLOW_ORDER = ["REFGROUT", "TOTIMPSB", "TOTEXPSB", "RECEIPTS", "PTRANSF",
                    "IPTRANSF", "TOTDEMO", "STOCKCH", "CLOSTLV", "STATDIFF"]

# Unit each flow must be expressed in before it can be summed across countries.
# JODI publishes every series in several units, including CONVBBL -- which is a
# barrels-per-tonne conversion factor, not a volume -- so aggregates must only
# add series that share the canonical unit.
JODI_CANONICAL_UNIT = {
    "CLOSTLV": "KBBL",
    "STOCKCH": "KBBL",
}
JODI_DEFAULT_UNIT = "KBD"
# Units that are never a volume for these flows and must never be selected.
JODI_INVALID_UNITS = {"CONVBBL"}


def _jodi_canonical_unit(flow: str) -> str:
    return JODI_CANONICAL_UNIT.get(flow, JODI_DEFAULT_UNIT)

jodi_cache: dict = {"data": {}, "ts": 0}
JODI_CACHE_TTL = 7200  # 2 hours


def _jodi_csv_path() -> str:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    return os.path.join(data_dir, "jodi_gasoline.csv")


def _load_jodi_country(country_code: str) -> dict:
    """Load JODI data for a single country from pre-processed CSV.
    Returns: {flow: {"unit": str, "entries": [(period, val)]}}
    """
    import csv
    csv_path = _jodi_csv_path()
    if not os.path.exists(csv_path):
        return {}

    result: dict = {}
    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) < 5 or row[0] != country_code:
                continue
            flow, unit, period, vs = row[1], row[2], row[3], row[4]
            val = None
            if vs not in ("", "x", "-", ".."):
                try:
                    val = float(vs)
                except ValueError:
                    pass
            if flow not in result:
                result[flow] = {"unit": unit, "entries": []}
            result[flow]["entries"].append((period, val))
    return result


def _load_jodi_region(region_code: str) -> dict:
    """Aggregate JODI data for all countries in a region.
    Returns same format as _load_jodi_country: {flow: {"unit": str, "entries": [(period, val)]}}
    Values are summed across countries for each period.
    """
    region = JODI_REGIONS[region_code]
    from collections import defaultdict
    # {flow: {period: total_value}}
    flow_periods: dict = defaultdict(lambda: defaultdict(float))
    flow_units: dict = {}
    flow_period_counts: dict = defaultdict(lambda: defaultdict(int))

    for cc in region["countries"]:
        cdata = _get_jodi_country(cc)
        if not cdata:
            continue
        for flow, fd in cdata.items():
            # Only sum series already in the flow's canonical unit -- adding a
            # KTONS/KL series (or a CONVBBL conversion factor) into a KBD total
            # silently corrupts the regional aggregate.
            if fd["unit"] != _jodi_canonical_unit(flow):
                continue
            if flow not in flow_units:
                flow_units[flow] = fd["unit"]
            for period, val in fd["entries"]:
                if val is not None:
                    flow_periods[flow][period] += val
                    flow_period_counts[flow][period] += 1

    result: dict = {}
    for flow in flow_periods:
        sorted_entries = sorted(flow_periods[flow].items())
        entries = [(p, round(v, 1)) for p, v in sorted_entries]
        if entries:
            result[flow] = {"unit": flow_units.get(flow, "KBD"), "entries": entries}
    return result


def _jodi_countries_list() -> dict:
    """Scan the JODI CSV to find which countries have data."""
    csv_path = _jodi_csv_path()
    if not os.path.exists(csv_path):
        return {}
    found = set()
    with open(csv_path, "r") as f:
        next(f)  # skip header
        for line in f:
            code = line.split(",", 1)[0]
            found.add(code)
    return {k: v for k, v in sorted(JODI_COUNTRY_NAMES.items(), key=lambda x: x[1]) if k in found}


def _download_jodi_refresh() -> dict:
    """Download fresh JODI data from website and update the CSV cache file."""
    import urllib.request
    import zipfile
    import csv as csv_mod
    import tempfile
    import shutil
    from collections import defaultdict

    PREFERRED = {
        "CLOSTLV": ["KBBL", "KBD", "KTONS"],
        "STOCKCH": ["KBBL", "KBD", "KTONS"],
    }
    DEFAULT_PREF = ["KBD", "KBBL", "KTONS"]

    url = "https://www.jodidata.org/_resources/files/downloads/oil-data/world_secondary_csv.zip"
    tmp_zip = os.path.join(tempfile.gettempdir(), "jodi_secondary.zip")
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "CrudeOilPlatform/1.0")
        with urllib.request.urlopen(req, timeout=300) as resp:
            with open(tmp_zip, "wb") as fp:
                shutil.copyfileobj(resp, fp, length=1 << 20)

        raw: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        with zipfile.ZipFile(tmp_zip) as zf:
            csv_name = zf.namelist()[0]
            with zf.open(csv_name) as f:
                reader = csv_mod.reader(
                    line.decode("utf-8", errors="replace") for line in f
                )
                header = next(reader)
                idx = {h: i for i, h in enumerate(header)}
                ep_i = idx.get("ENERGY_PRODUCT", 2)
                ra_i, tp_i = idx.get("REF_AREA", 0), idx.get("TIME_PERIOD", 1)
                fb_i, um_i, ov_i = idx.get("FLOW_BREAKDOWN", 3), idx.get("UNIT_MEASURE", 4), idx.get("OBS_VALUE", 5)
                for row in reader:
                    if len(row) <= ep_i or row[ep_i] != "GASOLINE":
                        continue
                    raw[row[ra_i]][row[fb_i]][row[um_i]].append((row[tp_i], row[ov_i]))

        # Pick preferred unit, write to CSV cache, and build result
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        csv_path = os.path.join(data_dir, "jodi_gasoline.csv")
        result: dict = {}
        with open(csv_path, "w") as fp:
            fp.write("country,flow,unit,period,value\n")
            for country in sorted(raw.keys()):
                result[country] = {}
                for flow, units_data in raw[country].items():
                    prefs = PREFERRED.get(flow, DEFAULT_PREF)
                    chosen = None
                    for u in prefs:
                        if u in units_data and any(v not in ("", "x", "-", "..") for _, v in units_data[u]):
                            chosen = u
                            break
                    if not chosen:
                        for u, entries in units_data.items():
                            if u in JODI_INVALID_UNITS:
                                continue
                            if any(v not in ("", "x", "-", "..") for _, v in entries):
                                chosen = u
                                break
                    if chosen:
                        entries = sorted(units_data[chosen])
                        parsed = []
                        for period, vs in entries:
                            val = None
                            if vs not in ("", "x", "-", ".."):
                                try:
                                    val = float(vs)
                                except ValueError:
                                    pass
                            fp.write(f"{country},{flow},{chosen},{period},{vs}\n")
                            parsed.append((period, val))
                        result[country][flow] = {"unit": chosen, "entries": parsed}
        return result
    finally:
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)


def _get_jodi_country(country_code: str) -> dict:
    """Get JODI gasoline data for one country (lazy, per-country cache)."""
    import time
    now = time.time()
    cache_key = country_code
    if cache_key in jodi_cache["data"]:
        entry = jodi_cache["data"][cache_key]
        if (now - entry["ts"]) < JODI_CACHE_TTL:
            return entry["flows"]
    flows = _load_jodi_country(country_code)
    if not flows and not os.path.exists(_jodi_csv_path()):
        _download_jodi_refresh()
        flows = _load_jodi_country(country_code)
    jodi_cache["data"][cache_key] = {"flows": flows, "ts": now}
    # Evict old entries if cache grows too large (keep last 10 countries)
    if len(jodi_cache["data"]) > 10:
        oldest = min(jodi_cache["data"], key=lambda k: jodi_cache["data"][k]["ts"])
        del jodi_cache["data"][oldest]
    return flows


@app.post("/api/jodi_refresh")
async def refresh_jodi_data():
    """Re-download JODI data from website (takes ~60s). Updates cached CSV."""
    try:
        data = _download_jodi_refresh()
        # Clear in-memory cache so _get_jodi_country re-reads from the updated CSV.
        # data is keyed {country: {flow: ...}} which is incompatible with the
        # per-country cache format {country: {"flows": ..., "ts": ...}}.
        jodi_cache["data"] = {}
        jodi_cache["ts"] = 0
        countries = len(data)
        return {"status": "ok", "countries": countries, "message": f"Refreshed JODI data for {countries} countries"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"JODI refresh error: {e}")


@app.get("/api/jodi_gasoline")
async def get_jodi_gasoline(
    country: str = Query("US", description="ISO2 country code or region code (R_EUROPE, R_MIDDLE_EAST, etc.)"),
    start_year: int = Query(2015, description="Start year"),
    end_year: int = Query(2026, description="End year"),
):
    """JODI gasoline S&D balance with multi-year overlay for any country or region."""
    is_region = country in JODI_REGIONS
    if not is_region and country not in JODI_COUNTRY_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown country/region: {country}")

    try:
        if is_region:
            country_data = _load_jodi_region(country)
        else:
            country_data = _get_jodi_country(country)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"JODI data error: {e}")

    from collections import defaultdict

    # Filter by year range and build series_map
    series_map: dict = {}
    for flow in JODI_FLOW_ORDER:
        fd = country_data.get(flow)
        if not fd:
            continue
        entries = []
        for period, val in fd["entries"]:
            if not period or len(period) < 7:
                continue
            try:
                yr = int(period[:4])
            except ValueError:
                continue
            if yr < start_year or yr > end_year:
                continue
            entries.append({"period": period, "value": val})
        if entries and any(e["value"] is not None for e in entries):
            series_map[flow] = {"unit": fd["unit"], "entries": entries}

    # Build S&D table
    snd_table = []
    for flow in JODI_FLOW_ORDER:
        if flow not in series_map:
            continue
        sm = series_map[flow]
        clean = [e["value"] for e in sm["entries"] if e["value"] is not None]
        if len(clean) < 2:
            continue
        latest = clean[-1]
        prev = clean[-2]
        chg = latest - prev
        # Period of the latest actual value -- trailing entries can be blank
        # when a country stops reporting, and labelling a stale value with the
        # newest period misstates the vintage.
        latest_period = next(
            (e["period"] for e in reversed(sm["entries"]) if e["value"] is not None),
            sm["entries"][-1]["period"],
        )
        n60 = min(len(clean), 60)
        avg5 = float(np.mean(clean[-n60:]))
        n12 = min(len(clean), 12)
        snd_table.append({
            "flow": flow,
            "flow_name": JODI_FLOW_NAMES.get(flow, flow),
            "units": sm["unit"],
            "latest": round(latest, 1),
            "latest_period": latest_period,
            "previous": round(prev, 1),
            "mom_change": round(chg, 1),
            "pct_change": round(chg / prev * 100, 2) if prev != 0 else 0,
            "avg_5y": round(avg5, 1),
            "vs_avg": round(latest - avg5, 1),
            "min_12m": round(min(clean[-n12:]), 1),
            "max_12m": round(max(clean[-n12:]), 1),
        })

    # Build multi-year overlay seasonal data
    MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    seasonal_overlay: dict = {}
    for flow in JODI_FLOW_ORDER:
        if flow not in series_map:
            continue
        sm = series_map[flow]
        year_data: dict = defaultdict(lambda: [None] * 12)
        for e in sm["entries"]:
            try:
                yr = int(e["period"][:4])
                mo = int(e["period"][5:7])
                if 1 <= mo <= 12:
                    year_data[yr][mo - 1] = e["value"]
            except (ValueError, IndexError):
                pass
        filtered = {}
        for yr, vals in sorted(year_data.items()):
            non_null = sum(1 for v in vals if v is not None)
            if non_null >= 4:
                filtered[str(yr)] = [round(v, 1) if v is not None else None for v in vals]
        if len(filtered) >= 2:
            seasonal_overlay[flow] = {
                "flow": flow,
                "flow_name": JODI_FLOW_NAMES.get(flow, flow),
                "units": sm["unit"],
                "months": MONTH_NAMES,
                "years": filtered,
            }

    # Build time-series for line charts
    chart_series: dict = {}
    for flow in JODI_FLOW_ORDER:
        if flow not in series_map:
            continue
        sm = series_map[flow]
        entries = sm["entries"]
        if len(entries) < 2:
            continue
        chart_series[flow] = {
            "flow": flow,
            "flow_name": JODI_FLOW_NAMES.get(flow, flow),
            "units": sm["unit"],
            "dates": [e["period"] for e in entries],
            "values": [round(e["value"], 1) if e["value"] is not None else None for e in entries],
        }

    # Available years from data
    all_years = set()
    for sm in series_map.values():
        for e in sm["entries"]:
            try:
                all_years.add(int(e["period"][:4]))
            except (ValueError, IndexError):
                pass

    # Build available list with regions at the top
    avail = _jodi_countries_list() or {k: v for k, v in sorted(JODI_COUNTRY_NAMES.items(), key=lambda x: x[1])}
    regions_avail = {code: info["name"] for code, info in JODI_REGIONS.items()}
    combined_available = {**regions_avail, **avail}

    display_name = JODI_REGIONS[country]["name"] if is_region else JODI_COUNTRY_NAMES.get(country, country)

    result = {
        "country": country,
        "country_name": display_name,
        "start_year": start_year,
        "end_year": end_year,
        "snd_table": snd_table,
        "seasonal_overlay": seasonal_overlay,
        "chart_series": chart_series,
        "available_years": sorted(all_years),
        "available_countries": combined_available,
    }

    if is_region:
        region_info = JODI_REGIONS[country]
        country_breakdown = []
        for cc in sorted(region_info["countries"]):
            cname = JODI_COUNTRY_NAMES.get(cc, cc)
            cd = _get_jodi_country(cc)
            row = {"code": cc, "name": cname, "flows": {}}
            for flow in JODI_FLOW_ORDER:
                fd = cd.get(flow)
                if not fd:
                    continue
                clean = [(p, v) for p, v in fd["entries"] if v is not None
                         and len(p) >= 7
                         and start_year <= int(p[:4]) <= end_year]
                if clean:
                    row["flows"][flow] = {
                        "latest": round(clean[-1][1], 1),
                        "latest_period": clean[-1][0],
                    }
            if row["flows"]:
                country_breakdown.append(row)
        result["is_region"] = True
        result["region_countries"] = country_breakdown

    return result


# =====================================================================
# FGE Global Gasoline Balances (from uploaded Excel)
# =====================================================================

FGE_REGIONS = ["North America", "Europe", "Latin America", "Middle East", "FSU", "Asia Pacific", "Africa"]
FGE_REGION_SHORT = {"North America": "NA", "Europe": "EU", "Latin America": "LA",
                     "Middle East": "ME", "FSU": "FSU", "Asia Pacific": "AP", "Africa": "AF"}
fge_cache: dict = {"data": None}


def _load_fge_data() -> dict:
    """Load FGE Product Balances Excel and extract gasoline data."""
    import openpyxl

    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    xlsx = os.path.join(data_dir, "fge_product_balances.xlsx")
    if not os.path.exists(xlsx):
        return {}

    wb = openpyxl.load_workbook(xlsx, data_only=True)

    # Sheet 1: "FGE Product Balances 01-May-26" — balance, MoM, YoY per region
    ws1 = wb[wb.sheetnames[0]]
    dates1 = []
    for c in range(2, ws1.max_column + 1):
        v = ws1.cell(28, c).value
        if v:
            dates1.append(v.strftime("%Y-%m"))

    sheet1 = {}
    row = 29
    for reg in FGE_REGIONS:
        balance = [ws1.cell(row, c).value for c in range(2, 2 + len(dates1))]
        mom = [ws1.cell(row + 1, c).value for c in range(2, 2 + len(dates1))]
        yoy = [ws1.cell(row + 2, c).value for c in range(2, 2 + len(dates1))]
        sheet1[reg] = {
            "balance": [round(v, 1) if v is not None else None for v in balance],
            "mom_change": [round(v, 1) if v is not None else None for v in mom],
            "yoy_change": [round(v, 1) if v is not None else None for v in yoy],
        }
        row += 3

    # Sheet 2: "FGE Product Balances SnD" — balance, supply, demand per region
    ws2 = wb[wb.sheetnames[1]]
    dates2 = []
    for c in range(2, ws2.max_column + 1):
        v = ws2.cell(28, c).value
        if v:
            dates2.append(v.strftime("%Y-%m"))

    sheet2 = {}
    row = 29
    for reg in FGE_REGIONS:
        balance = [ws2.cell(row, c).value for c in range(2, 2 + len(dates2))]
        supply = [ws2.cell(row + 1, c).value for c in range(2, 2 + len(dates2))]
        demand = [ws2.cell(row + 2, c).value for c in range(2, 2 + len(dates2))]
        sheet2[reg] = {
            "balance": [round(v, 1) if v is not None else None for v in balance],
            "supply": [round(v, 1) if v is not None else None for v in supply],
            "demand": [round(v, 1) if v is not None else None for v in demand],
        }
        row += 3

    # Compute Global totals
    global_bal1 = [round(sum(sheet1[r]["balance"][i] or 0 for r in FGE_REGIONS), 1) for i in range(len(dates1))]
    global_mom1 = [round(sum(sheet1[r]["mom_change"][i] or 0 for r in FGE_REGIONS), 1) for i in range(len(dates1))]
    global_yoy1 = [round(sum(sheet1[r]["yoy_change"][i] or 0 for r in FGE_REGIONS), 1) for i in range(len(dates1))]
    sheet1["Global"] = {"balance": global_bal1, "mom_change": global_mom1, "yoy_change": global_yoy1}

    global_bal2 = [round(sum(sheet2[r]["balance"][i] or 0 for r in FGE_REGIONS), 1) for i in range(len(dates2))]
    global_sup2 = [round(sum(sheet2[r]["supply"][i] or 0 for r in FGE_REGIONS), 1) for i in range(len(dates2))]
    global_dem2 = [round(sum(sheet2[r]["demand"][i] or 0 for r in FGE_REGIONS), 1) for i in range(len(dates2))]
    sheet2["Global"] = {"balance": global_bal2, "supply": global_sup2, "demand": global_dem2}

    # Quarterly YoY aggregation for stacked bar chart (from sheet1 which has YoY data)
    quarterly_yoy: dict = {}
    for i, d in enumerate(dates1):
        yr, mo = int(d[:4]), int(d[5:7])
        q = (mo - 1) // 3 + 1
        qkey = f"{q}Q {str(yr)[2:]}"
        if qkey not in quarterly_yoy:
            quarterly_yoy[qkey] = {r: [] for r in FGE_REGIONS}
            quarterly_yoy[qkey]["_count"] = 0
        quarterly_yoy[qkey]["_count"] += 1
        for r in FGE_REGIONS:
            v = sheet1[r]["yoy_change"][i]
            if v is not None:
                quarterly_yoy[qkey][r].append(v)

    qyoy_labels = list(quarterly_yoy.keys())
    qyoy_regions: dict = {}
    for r in FGE_REGIONS:
        qyoy_regions[FGE_REGION_SHORT[r]] = [
            round(np.mean(quarterly_yoy[q][r]), 1) if quarterly_yoy[q][r] else 0
            for q in qyoy_labels
        ]
    qyoy_total = [
        round(sum(qyoy_regions[FGE_REGION_SHORT[r]][i] for r in FGE_REGIONS), 1)
        for i in range(len(qyoy_labels))
    ]

    # Seasonal overlay: group balance by year and month for each region+global
    seasonal = {}
    all_regions = FGE_REGIONS + ["Global"]
    for reg in all_regions:
        year_months: dict = {}
        for i, d in enumerate(dates2):
            yr, mo = int(d[:4]), int(d[5:7])
            if yr not in year_months:
                year_months[yr] = [None] * 12
            year_months[yr][mo - 1] = sheet2[reg]["balance"][i]
        seasonal[reg] = {str(yr): vals for yr, vals in sorted(year_months.items())}

    return {
        "dates_outlook": dates1,
        "dates_snd": dates2,
        "outlook": sheet1,
        "snd": sheet2,
        "quarterly_yoy": {"labels": qyoy_labels, "regions": qyoy_regions, "total": qyoy_total},
        "seasonal": seasonal,
        "regions": FGE_REGIONS,
    }


def _get_fge_data() -> dict:
    if fge_cache["data"] is None:
        fge_cache["data"] = _load_fge_data()
    return fge_cache["data"]


@app.get("/api/fge_gasoline")
async def get_fge_gasoline(region: str = Query("Global", description="Region or Global")):
    """FGE Global Gasoline S/D Balances by region."""
    data = _get_fge_data()
    if not data:
        raise HTTPException(status_code=404, detail="FGE data file not found. Upload fge_product_balances.xlsx to data/")

    valid = FGE_REGIONS + ["Global"]
    if region not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown region: {region}. Valid: {valid}")

    outlook = data["outlook"].get(region, {})
    snd = data["snd"].get(region, {})
    seasonal = data["seasonal"].get(region, {})

    # Build regional comparison for latest available month
    region_comparison = []
    for r in FGE_REGIONS:
        s = data["snd"].get(r, {})
        bal_vals = [v for v in (s.get("balance") or []) if v is not None]
        sup_vals = [v for v in (s.get("supply") or []) if v is not None]
        dem_vals = [v for v in (s.get("demand") or []) if v is not None]
        ol = data["outlook"].get(r, {})
        yoy_vals = [v for v in (ol.get("yoy_change") or []) if v is not None]
        region_comparison.append({
            "region": r,
            "short": FGE_REGION_SHORT[r],
            "latest_balance": bal_vals[-1] if bal_vals else None,
            "latest_supply": sup_vals[-1] if sup_vals else None,
            "latest_demand": dem_vals[-1] if dem_vals else None,
            "latest_yoy": yoy_vals[-1] if yoy_vals else None,
        })

    return {
        "region": region,
        "dates_outlook": data["dates_outlook"],
        "dates_snd": data["dates_snd"],
        "balance": outlook.get("balance", []),
        "mom_change": outlook.get("mom_change", []),
        "yoy_change": outlook.get("yoy_change", []),
        "supply": snd.get("supply", []),
        "demand": snd.get("demand", []),
        "snd_balance": snd.get("balance", []),
        "seasonal": seasonal,
        "quarterly_yoy": data["quarterly_yoy"],
        "region_comparison": region_comparison,
        "available_regions": valid,
    }


# =============================================================================
# KPLER API INTEGRATION
# =============================================================================
_kpler_sdk_loaded = False
_kpler_flows_client = None
_kpler_products_client = None

def _ensure_kpler():
    """Lazy-load Kpler SDK and create clients."""
    global _kpler_sdk_loaded, _kpler_flows_client, _kpler_products_client
    if _kpler_sdk_loaded:
        return _kpler_flows_client is not None
    _kpler_sdk_loaded = True
    try:
        from kpler.sdk.configuration import Configuration
        from kpler.sdk import Platform
        from kpler.sdk.resources.flows import Flows
        from kpler.sdk.resources.products import Products
        username = os.environ.get("KPLER_USERNAME", "")
        password = os.environ.get("KPLER_PASSWORD", "")
        if not username or not password:
            print("KPLER: No credentials found (KPLER_USERNAME/KPLER_PASSWORD)")
            return False
        config = Configuration(Platform.Liquids, username, password)
        _kpler_flows_client = Flows(config)
        _kpler_products_client = Products(config)
        print(f"KPLER: SDK initialized for {username}")
        return True
    except Exception as e:
        print(f"KPLER: SDK init failed: {e}")
        return False


def _kpler_melt(df, var_name="location"):
    """Convert Kpler wide-format response to long format."""
    df = df.copy()
    if "Period End Date" in df.columns:
        df.drop(columns=["Period End Date"], inplace=True)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df.rename(columns={"Date": "date"}, inplace=True)
    elif "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.melt(id_vars=["date"], var_name=var_name, value_name="value")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


@app.get("/api/kpler/status")
async def kpler_status():
    """Check if Kpler SDK is available and credentials are set."""
    ok = _ensure_kpler()
    return {"available": ok, "message": "Kpler SDK ready" if ok else "Kpler credentials not configured"}


@app.get("/api/kpler/flows")
async def get_kpler_flows(
    product: str = "Gasoline",
    direction: str = "export",
    split: str = "OriginCountries",
    granularity: str = "monthly",
    unit: str = "kbd",
    start_date: str = "2020-01-01",
    end_date: str = "2026-12-31",
    from_zone: str = "",
    to_zone: str = "",
    with_forecast: bool = True,
    with_intra_country: bool = False,
):
    """Fetch Kpler flows data via SDK."""
    if not _ensure_kpler():
        raise HTTPException(status_code=503, detail="Kpler SDK not available. Set KPLER_USERNAME and KPLER_PASSWORD.")

    from kpler.sdk import FlowsDirection, FlowsMeasurementUnit, FlowsPeriod, FlowsSplit
    from datetime import date as dt_date

    direction_map = {
        "export": FlowsDirection.Export,
        "import": FlowsDirection.Import,
    }
    split_map = {
        "OriginCountries": FlowsSplit.OriginCountries,
        "DestinationCountries": FlowsSplit.DestinationCountries,
        "OriginPadds": FlowsSplit.OriginPadds,
        "DestinationPadds": FlowsSplit.DestinationPadds,
        "OriginContinents": FlowsSplit.OriginContinents,
        "DestinationContinents": FlowsSplit.DestinationContinents,
        "OriginTradingRegions": FlowsSplit.OriginTradingRegions,
        "DestinationTradingRegions": FlowsSplit.DestinationTradingRegions,
        "Products": FlowsSplit.Products,
        "Grades": FlowsSplit.Grades,
        "VesselTypeOil": FlowsSplit.VesselTypeOil,
        "Total": FlowsSplit.Total,
    }
    granularity_map = {
        "daily": FlowsPeriod.Daily,
        "weekly": FlowsPeriod.EiaWeekly,
        "monthly": FlowsPeriod.Monthly,
    }
    unit_map = {
        "kbd": FlowsMeasurementUnit.KBD,
        "kb": FlowsMeasurementUnit.KB,
    }

    try:
        s = start_date.split("-")
        e = end_date.split("-")
        sd = dt_date(int(s[0]), int(s[1]), int(s[2]))
        ed = dt_date(int(e[0]), int(e[1]), int(e[2]))

        params = {
            "flow_direction": [direction_map.get(direction.lower(), FlowsDirection.Export)],
            "split": [split_map.get(split, FlowsSplit.OriginCountries)],
            "granularity": [granularity_map.get(granularity.lower(), FlowsPeriod.Monthly)],
            "unit": [unit_map.get(unit.lower(), FlowsMeasurementUnit.KBD)],
            "start_date": sd,
            "end_date": ed,
            "with_forecast": with_forecast,
            "with_intra_country": with_intra_country,
            "products": [product],
        }
        if from_zone:
            params["from_zones"] = [from_zone]
        if to_zone:
            params["to_zones"] = [to_zone]

        df = _kpler_flows_client.get(**params)
        long_df = _kpler_melt(df, var_name="location")
        long_df = long_df[long_df["location"] != "Total"].copy()
        long_df = long_df.dropna(subset=["value"])

        # Build pivot for charts (date x location)
        pivot = long_df.pivot_table(index="date", columns="location", values="value", aggfunc="sum").round(2)
        pivot = pivot.fillna(0)

        # Top locations by total volume
        totals = pivot.sum().sort_values(ascending=False)
        top_locations = list(totals.head(30).index)

        # Time series for top locations
        series_data = {}
        for loc in top_locations:
            if loc in pivot.columns:
                s = pivot[loc]
                series_data[loc] = {
                    "dates": [d.strftime("%Y-%m-%d") for d in s.index],
                    "values": [round(v, 2) if not pd.isna(v) else 0 for v in s.values],
                    "total": round(float(totals[loc]), 2),
                }

        # For "latest", use the most recent complete month (skip partials)
        # A partial month typically has much lower values, so use the latest
        # month where total flows are >50% of the prior month average
        def _best_latest(s):
            nz = s[s > 0]
            if len(nz) < 2:
                return float(nz.iloc[-1]) if len(nz) > 0 else 0
            # If last value is less than 30% of second-to-last, it's likely partial
            if nz.iloc[-1] < nz.iloc[-2] * 0.3:
                return float(nz.iloc[-2])
            return float(nz.iloc[-1])

        # Summary table
        summary = []
        for loc in top_locations:
            if loc in pivot.columns:
                s = pivot[loc]
                vals = s[s > 0]
                summary.append({
                    "location": loc,
                    "latest": round(_best_latest(s), 2),
                    "avg": round(float(vals.mean()) if len(vals) > 0 else 0, 2),
                    "max": round(float(vals.max()) if len(vals) > 0 else 0, 2),
                    "min": round(float(vals.min()) if len(vals) > 0 else 0, 2),
                    "total": round(float(totals[loc]), 2),
                })

        # Seasonal overlay (monthly: group by month of year, one line per year)
        seasonal = {}
        if granularity.lower() == "monthly":
            long_df["year"] = long_df["date"].dt.year
            long_df["month"] = long_df["date"].dt.month
            agg = long_df.groupby(["year", "month"])["value"].sum().reset_index()
            for yr in sorted(agg["year"].unique()):
                yr_data = agg[agg["year"] == yr].sort_values("month")
                seasonal[str(yr)] = {
                    "months": list(yr_data["month"].astype(int)),
                    "values": [round(v, 2) for v in yr_data["value"]],
                }

        return {
            "product": product,
            "direction": direction,
            "split": split,
            "granularity": granularity,
            "unit": unit,
            "locations": top_locations,
            "series": series_data,
            "summary": summary,
            "seasonal": seasonal,
            "total_locations": int(len(totals)),
            "date_range": {
                "start": long_df["date"].min().strftime("%Y-%m-%d") if len(long_df) > 0 else start_date,
                "end": long_df["date"].max().strftime("%Y-%m-%d") if len(long_df) > 0 else end_date,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kpler API error: {str(e)}")


@app.get("/api/kpler/products")
async def get_kpler_products():
    """List available Kpler products for gasoline/naphtha."""
    if not _ensure_kpler():
        raise HTTPException(status_code=503, detail="Kpler SDK not available.")
    try:
        prods = _kpler_products_client.get()
        # Filter to gasoline-related
        gas = prods[
            prods["Product"].str.contains("Gasoline|Naphtha", case=False, na=False) |
            prods["Name"].str.contains("RBOB|CBOB|Gasoline|Naphtha|Avgas", case=False, na=False)
        ]
        result = []
        for _, row in gas.iterrows():
            result.append({
                "id": int(row.get("Id (Product)", 0)),
                "name": str(row.get("Name", "")),
                "family": str(row.get("Family", "")),
                "group": str(row.get("Group", "")),
                "product": str(row.get("Product", "")),
            })
        return {"products": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kpler products error: {str(e)}")


@app.get("/api/kpler/gasoline_dashboard")
async def get_kpler_gasoline_dashboard(
    start_year: int = 2020,
    end_year: int = 2026,
    zone: str = "",
):
    """Comprehensive gasoline dashboard pulling multiple Kpler queries."""
    if not _ensure_kpler():
        raise HTTPException(status_code=503, detail="Kpler SDK not available.")

    from kpler.sdk import FlowsDirection, FlowsMeasurementUnit, FlowsPeriod, FlowsSplit
    from datetime import date as dt_date

    sd = dt_date(start_year, 1, 1)
    ed = dt_date(end_year, 12, 31)

    results = {}
    queries = [
        ("exports_by_origin", FlowsDirection.Export, FlowsSplit.OriginCountries, None, None),
        ("imports_by_destination", FlowsDirection.Import, FlowsSplit.DestinationCountries, None, None),
        ("exports_by_destination", FlowsDirection.Export, FlowsSplit.DestinationCountries, None, None),
    ]

    # If zone specified, add zone-specific queries
    if zone:
        queries.append(("zone_exports_by_dest", FlowsDirection.Export, FlowsSplit.DestinationCountries, zone, None))
        queries.append(("zone_imports_by_origin", FlowsDirection.Import, FlowsSplit.OriginCountries, None, zone))

    for name, direction, split, from_z, to_z in queries:
        try:
            params = {
                "flow_direction": [direction],
                "split": [split],
                "granularity": [FlowsPeriod.Monthly],
                "unit": [FlowsMeasurementUnit.KBD],
                "start_date": sd,
                "end_date": ed,
                "with_forecast": True,
                "with_intra_country": False,
                "products": ["Gasoline"],
            }
            if from_z:
                params["from_zones"] = [from_z]
            if to_z:
                params["to_zones"] = [to_z]

            df = _kpler_flows_client.get(**params)
            long_df = _kpler_melt(df, var_name="location")
            long_df = long_df[long_df["location"] != "Total"].copy()
            long_df = long_df.dropna(subset=["value"])

            pivot = long_df.pivot_table(index="date", columns="location", values="value", aggfunc="sum").round(2).fillna(0)
            totals = pivot.sum().sort_values(ascending=False)
            top = list(totals.head(20).index)

            series = {}
            for loc in top:
                if loc in pivot.columns:
                    s = pivot[loc]
                    series[loc] = {
                        "dates": [d.strftime("%Y-%m-%d") for d in s.index],
                        "values": [round(v, 2) if not pd.isna(v) else 0 for v in s.values],
                    }

            # Seasonal overlay
            seasonal = {}
            long_df["year"] = long_df["date"].dt.year
            long_df["month"] = long_df["date"].dt.month
            agg = long_df.groupby(["year", "month"])["value"].sum().reset_index()
            for yr in sorted(agg["year"].unique()):
                yr_data = agg[agg["year"] == yr].sort_values("month")
                seasonal[str(yr)] = {
                    "months": list(yr_data["month"].astype(int)),
                    "values": [round(v, 2) for v in yr_data["value"]],
                }

            # Summary
            summary = []
            for loc in top:
                if loc in pivot.columns:
                    s = pivot[loc]
                    vals = s[s > 0]
                    latest = float(vals.iloc[-1]) if len(vals) > 0 else 0
                    avg = float(vals.mean()) if len(vals) > 0 else 0
                    summary.append({
                        "location": loc,
                        "latest": round(latest, 2),
                        "avg": round(avg, 2),
                        "mom_change": round(float(s.iloc[-1] - s.iloc[-2]), 2) if len(s) >= 2 else 0,
                        "mom_pct": round(float((s.iloc[-1] - s.iloc[-2]) / s.iloc[-2] * 100), 2) if len(s) >= 2 and s.iloc[-2] != 0 else 0,
                    })

            results[name] = {
                "locations": top,
                "series": series,
                "summary": summary,
                "seasonal": seasonal,
            }
        except Exception as e:
            results[name] = {"error": str(e)}

    return {
        "zone": zone or "Global",
        "start_year": start_year,
        "end_year": end_year,
        "data": results,
    }


# ---------------------------------------------------------------------------
# Kpler Refinery Trade Flows — Installation-Level
# ---------------------------------------------------------------------------

_KPLER_PRODUCTS_LIST = ["Gasoline", "Naphtha", "Crude", "Gasoil", "Diesel", "Jet", "Kerosene", "Fuel Oil"]
_KPLER_REGIONS = {
    "US": "United States",
    "NWE": "North West Europe Zone",
    "MED": "MED Zone (MED Sea+Black Sea)",
    "Asia": "Eastern Asia",
    "India": "India",
    "Middle East": "Middle East",
    "West Africa": "Western Africa",
    "Latin America": "Latin America",
    "Canada": "Canada",
    "Southeast Asia": "South-East Asia",
    "Russia/FSU": "Former Soviet Union",
}


@app.get("/api/kpler/refinery_flows")
async def get_kpler_refinery_flows(
    product: str = "Gasoline",
    direction: str = "export",
    region: str = "US",
    granularity: str = "monthly",
    start_date: str = "2024-01-01",
    end_date: str = "2026-12-31",
):
    """Get trade flows split by installation (refinery/terminal) for a region."""
    if not _ensure_kpler():
        raise HTTPException(status_code=503, detail="Kpler SDK not available.")

    from kpler.sdk import FlowsDirection, FlowsMeasurementUnit, FlowsPeriod, FlowsSplit
    from datetime import date as dt_date

    direction_enum = FlowsDirection.Export if direction.lower() == "export" else FlowsDirection.Import
    # Exports: split by origin installations (domestic refineries)
    # Imports: split by origin installations (foreign refineries sending TO this region)
    split_enum = FlowsSplit.OriginInstallations
    gran_map = {"daily": FlowsPeriod.Daily, "weekly": FlowsPeriod.EiaWeekly, "monthly": FlowsPeriod.Monthly}

    zone_name = _KPLER_REGIONS.get(region, region)

    try:
        s = start_date.split("-")
        e = end_date.split("-")
        sd = dt_date(int(s[0]), int(s[1]), int(s[2]))
        ed = dt_date(int(e[0]), int(e[1]), int(e[2]))

        params = {
            "flow_direction": [direction_enum],
            "split": [split_enum],
            "granularity": [gran_map.get(granularity, FlowsPeriod.Monthly)],
            "unit": [FlowsMeasurementUnit.KBD],
            "start_date": sd,
            "end_date": ed,
            "products": [product],
            "with_forecast": False,
            "with_intra_country": False,
        }
        if direction.lower() == "export":
            params["from_zones"] = [zone_name]
        else:
            params["to_zones"] = [zone_name]

        df = _kpler_flows_client.get(**params)
        long_df = _kpler_melt(df, var_name="installation")
        long_df = long_df[long_df["installation"] != "Total"].copy()
        long_df = long_df.dropna(subset=["value"])

        pivot = long_df.pivot_table(index="date", columns="installation", values="value", aggfunc="sum").round(2).fillna(0)
        totals = pivot.sum().sort_values(ascending=False)
        top = list(totals.head(25).index)

        # Determine latest actual month (exclude current partial month)
        from datetime import datetime as dt_datetime
        today = dt_datetime.utcnow().date()
        first_of_month = today.replace(day=1)
        last_complete = (first_of_month - pd.Timedelta(days=1))  # last day of prev month
        last_actual_cutoff = last_complete.replace(day=1)  # first day of last complete month
        # Filter pivot to only complete months for "latest" calculations
        actual_dates = [d for d in pivot.index if d < pd.Timestamp(first_of_month)]
        latest_actual_date = actual_dates[-1] if actual_dates else (pivot.index[-1] if len(pivot) > 0 else None)
        latest_date_str = latest_actual_date.strftime("%B %Y") if latest_actual_date is not None else "N/A"

        series = {}
        for inst in top:
            if inst in pivot.columns:
                sv = pivot[inst]
                series[inst] = {
                    "dates": [d.strftime("%Y-%m-%d") for d in sv.index],
                    "values": [round(v, 2) if not pd.isna(v) else 0 for v in sv.values],
                    "total": round(float(totals[inst]), 2),
                }

        summary = []
        for inst in top:
            if inst in pivot.columns:
                sv = pivot[inst]
                # Use latest actual month (not current partial)
                actual_sv = sv.loc[[d for d in sv.index if d < pd.Timestamp(first_of_month)]]
                vals = actual_sv[actual_sv > 0]
                latest = float(vals.iloc[-1]) if len(vals) > 0 else 0
                prev = float(vals.iloc[-2]) if len(vals) >= 2 else latest
                avg_val = float(vals.mean()) if len(vals) > 0 else 0
                summary.append({
                    "installation": inst,
                    "latest": round(latest, 2),
                    "avg": round(avg_val, 2),
                    "max": round(float(vals.max()), 2) if len(vals) > 0 else 0,
                    "change": round(latest - prev, 2),
                    "change_pct": round((latest - prev) / prev * 100, 2) if prev > 0 else 0,
                    "total": round(float(totals[inst]), 2),
                })

        # Seasonal overlay
        seasonal = {}
        long_df["year"] = long_df["date"].dt.year
        long_df["month"] = long_df["date"].dt.month
        total_by_ym = long_df.groupby(["year", "month"])["value"].sum().reset_index()
        for yr in sorted(total_by_ym["year"].unique()):
            yr_data = total_by_ym[total_by_ym["year"] == yr].sort_values("month")
            seasonal[str(yr)] = {
                "months": list(yr_data["month"].astype(int)),
                "values": [round(v, 2) for v in yr_data["value"]],
            }

        return {
            "product": product,
            "direction": direction,
            "region": region,
            "zone_name": zone_name,
            "installations": top,
            "series": series,
            "summary": summary,
            "seasonal": seasonal,
            "total_installations": int(len(totals)),
            "latest_date": latest_date_str,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kpler refinery flows error: {str(e)}")


@app.get("/api/kpler/refinery_destinations")
async def get_kpler_refinery_destinations(
    product: str = "Gasoline",
    region: str = "US",
    installation: str = "",
    granularity: str = "monthly",
    start_date: str = "2024-01-01",
    end_date: str = "2026-12-31",
    split_by: str = "DestinationTradingRegions",
):
    """Get where a region's (or specific installation's) exports go."""
    if not _ensure_kpler():
        raise HTTPException(status_code=503, detail="Kpler SDK not available.")

    from kpler.sdk import FlowsDirection, FlowsMeasurementUnit, FlowsPeriod, FlowsSplit
    from datetime import date as dt_date

    split_map = {
        "DestinationTradingRegions": FlowsSplit.DestinationTradingRegions,
        "DestinationCountries": FlowsSplit.DestinationCountries,
        "DestinationContinents": FlowsSplit.DestinationContinents,
    }
    gran_map = {"daily": FlowsPeriod.Daily, "weekly": FlowsPeriod.EiaWeekly, "monthly": FlowsPeriod.Monthly}

    zone_name = _KPLER_REGIONS.get(region, region)

    try:
        s = start_date.split("-")
        e = end_date.split("-")
        sd = dt_date(int(s[0]), int(s[1]), int(s[2]))
        ed = dt_date(int(e[0]), int(e[1]), int(e[2]))

        params = {
            "flow_direction": [FlowsDirection.Export],
            "split": [split_map.get(split_by, FlowsSplit.DestinationTradingRegions)],
            "granularity": [gran_map.get(granularity, FlowsPeriod.Monthly)],
            "unit": [FlowsMeasurementUnit.KBD],
            "start_date": sd,
            "end_date": ed,
            "products": [product],
            "with_forecast": False,
            "with_intra_country": False,
        }
        if installation:
            params["from_installations"] = [installation]
        else:
            params["from_zones"] = [zone_name]

        df = _kpler_flows_client.get(**params)
        long_df = _kpler_melt(df, var_name="destination")
        long_df = long_df[long_df["destination"] != "Total"].copy()
        long_df = long_df.dropna(subset=["value"])

        pivot = long_df.pivot_table(index="date", columns="destination", values="value", aggfunc="sum").round(2).fillna(0)
        totals = pivot.sum().sort_values(ascending=False)
        top = list(totals.head(20).index)

        series = {}
        for dest in top:
            if dest in pivot.columns:
                sv = pivot[dest]
                series[dest] = {
                    "dates": [d.strftime("%Y-%m-%d") for d in sv.index],
                    "values": [round(v, 2) if not pd.isna(v) else 0 for v in sv.values],
                    "total": round(float(totals[dest]), 2),
                }

        summary = []
        for dest in top:
            if dest in pivot.columns:
                sv = pivot[dest]
                vals = sv[sv > 0]
                latest = float(vals.iloc[-1]) if len(vals) > 0 else 0
                avg_val = float(vals.mean()) if len(vals) > 0 else 0
                summary.append({
                    "destination": dest,
                    "latest": round(latest, 2),
                    "avg": round(avg_val, 2),
                    "total": round(float(totals[dest]), 2),
                    "share_pct": round(float(totals[dest]) / float(totals.sum()) * 100, 1) if totals.sum() > 0 else 0,
                })

        # Seasonal
        seasonal = {}
        long_df["year"] = long_df["date"].dt.year
        long_df["month"] = long_df["date"].dt.month
        total_by_ym = long_df.groupby(["year", "month"])["value"].sum().reset_index()
        for yr in sorted(total_by_ym["year"].unique()):
            yr_data = total_by_ym[total_by_ym["year"] == yr].sort_values("month")
            seasonal[str(yr)] = {
                "months": list(yr_data["month"].astype(int)),
                "values": [round(v, 2) for v in yr_data["value"]],
            }

        return {
            "product": product,
            "region": region,
            "installation": installation or "All",
            "split_by": split_by,
            "destinations": top,
            "series": series,
            "summary": summary,
            "seasonal": seasonal,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kpler destinations error: {str(e)}")


@app.get("/api/kpler/refinery_detail")
async def get_kpler_refinery_detail(
    installation: str = "",
    start_date: str = "2024-01-01",
    end_date: str = "2026-12-31",
):
    """Get detailed trade data for a single installation — exports by product + destinations."""
    if not _ensure_kpler():
        raise HTTPException(status_code=503, detail="Kpler SDK not available.")
    if not installation:
        raise HTTPException(status_code=400, detail="installation parameter required")

    from kpler.sdk import FlowsDirection, FlowsMeasurementUnit, FlowsPeriod, FlowsSplit
    from datetime import date as dt_date

    s = start_date.split("-")
    e = end_date.split("-")
    sd = dt_date(int(s[0]), int(s[1]), int(s[2]))
    ed = dt_date(int(e[0]), int(e[1]), int(e[2]))

    results = {}

    # 1. Exports by product
    try:
        df_prod = _kpler_flows_client.get(
            flow_direction=[FlowsDirection.Export],
            split=[FlowsSplit.Products],
            granularity=[FlowsPeriod.Monthly],
            unit=[FlowsMeasurementUnit.KBD],
            start_date=sd, end_date=ed,
            from_installations=[installation],
            with_forecast=False,
        )
        long_prod = _kpler_melt(df_prod, var_name="product")
        long_prod = long_prod[long_prod["product"] != "Total"].dropna(subset=["value"])
        pivot_p = long_prod.pivot_table(index="date", columns="product", values="value", aggfunc="sum").round(2).fillna(0)
        totals_p = pivot_p.sum().sort_values(ascending=False)
        products_data = {}
        for p in totals_p.index:
            sv = pivot_p[p]
            products_data[p] = {
                "dates": [d.strftime("%Y-%m-%d") for d in sv.index],
                "values": [round(v, 2) for v in sv.values],
                "total": round(float(totals_p[p]), 2),
            }
        results["exports_by_product"] = products_data
    except Exception as e:
        results["exports_by_product"] = {"error": str(e)}

    # 2. Exports by destination country
    try:
        df_dest = _kpler_flows_client.get(
            flow_direction=[FlowsDirection.Export],
            split=[FlowsSplit.DestinationCountries],
            granularity=[FlowsPeriod.Monthly],
            unit=[FlowsMeasurementUnit.KBD],
            start_date=sd, end_date=ed,
            from_installations=[installation],
            with_forecast=False,
        )
        long_dest = _kpler_melt(df_dest, var_name="country")
        long_dest = long_dest[long_dest["country"] != "Total"].dropna(subset=["value"])
        pivot_d = long_dest.pivot_table(index="date", columns="country", values="value", aggfunc="sum").round(2).fillna(0)
        totals_d = pivot_d.sum().sort_values(ascending=False)
        destinations_data = {}
        for c in list(totals_d.head(15).index):
            sv = pivot_d[c]
            destinations_data[c] = {
                "dates": [d.strftime("%Y-%m-%d") for d in sv.index],
                "values": [round(v, 2) for v in sv.values],
                "total": round(float(totals_d[c]), 2),
                "share_pct": round(float(totals_d[c]) / float(totals_d.sum()) * 100, 1) if totals_d.sum() > 0 else 0,
            }
        results["exports_by_destination"] = destinations_data
    except Exception as e:
        results["exports_by_destination"] = {"error": str(e)}

    # 3. Imports by product (what the installation receives)
    try:
        df_imp = _kpler_flows_client.get(
            flow_direction=[FlowsDirection.Import],
            split=[FlowsSplit.Products],
            granularity=[FlowsPeriod.Monthly],
            unit=[FlowsMeasurementUnit.KBD],
            start_date=sd, end_date=ed,
            to_installations=[installation],
            with_forecast=False,
        )
        long_imp = _kpler_melt(df_imp, var_name="product")
        long_imp = long_imp[long_imp["product"] != "Total"].dropna(subset=["value"])
        pivot_i = long_imp.pivot_table(index="date", columns="product", values="value", aggfunc="sum").round(2).fillna(0)
        totals_i = pivot_i.sum().sort_values(ascending=False)
        imports_data = {}
        for p in totals_i.index:
            sv = pivot_i[p]
            imports_data[p] = {
                "dates": [d.strftime("%Y-%m-%d") for d in sv.index],
                "values": [round(v, 2) for v in sv.values],
                "total": round(float(totals_i[p]), 2),
            }
        results["imports_by_product"] = imports_data
    except Exception as e:
        results["imports_by_product"] = {"error": str(e)}

    return {"installation": installation, "data": results}


@app.get("/api/kpler/region_list")
async def get_kpler_region_list():
    """Return available regions for the trade flow tab."""
    return {
        "regions": _KPLER_REGIONS,
        "products": _KPLER_PRODUCTS_LIST,
        "split_options": [
            {"value": "DestinationTradingRegions", "label": "Trading Regions"},
            {"value": "DestinationCountries", "label": "Countries"},
            {"value": "DestinationContinents", "label": "Continents"},
        ],
    }


@app.get("/api/kpler/refinery_search")
async def kpler_refinery_search(q: str = ""):
    """Search Kpler installations by name for the refinery explorer."""
    if not _ensure_kpler():
        raise HTTPException(status_code=503, detail="Kpler SDK not available.")
    if not q or len(q) < 2:
        return {"results": []}
    try:
        from kpler.sdk.resources.zones import Zones
        from kpler.sdk import Platform
        from kpler.sdk.configuration import Configuration
        username = os.environ.get("KPLER_USERNAME", "")
        password = os.environ.get("KPLER_PASSWORD", "")
        config = Configuration(Platform.Liquids, username, password)
        zones_client = Zones(config)
        df = zones_client.search(q)
        results = df["zones"].tolist() if "zones" in df.columns else []
        return {"results": results[:20]}
    except Exception as e:
        return {"results": [], "error": str(e)}


@app.get("/api/kpler/refinery_explorer")
async def kpler_refinery_explorer(
    installation: str = "",
    start_date: str = "2023-01-01",
    end_date: str = "2026-12-31",
):
    """Full refinery explorer: exports by product + destination, imports by product + origin."""
    if not _ensure_kpler():
        raise HTTPException(status_code=503, detail="Kpler SDK not available.")
    if not installation:
        raise HTTPException(status_code=400, detail="installation parameter required")

    from kpler.sdk import FlowsDirection, FlowsMeasurementUnit, FlowsPeriod, FlowsSplit
    from datetime import date as dt_date

    s = start_date.split("-")
    e = end_date.split("-")
    sd = dt_date(int(s[0]), int(s[1]), int(s[2]))
    ed = dt_date(int(e[0]), int(e[1]), int(e[2]))

    results = {}

    # 1. Exports by product
    try:
        df_prod = _kpler_flows_client.get(
            flow_direction=[FlowsDirection.Export],
            split=[FlowsSplit.Products],
            granularity=[FlowsPeriod.Monthly],
            unit=[FlowsMeasurementUnit.KBD],
            start_date=sd, end_date=ed,
            from_installations=[installation],
            with_forecast=False,
        )
        long_prod = _kpler_melt(df_prod, var_name="product")
        long_prod = long_prod[long_prod["product"] != "Total"].dropna(subset=["value"])
        pivot_p = long_prod.pivot_table(index="date", columns="product", values="value", aggfunc="sum").round(2).fillna(0)
        totals_p = pivot_p.sum().sort_values(ascending=False)
        products_data = {}
        for p in totals_p.index:
            sv = pivot_p[p]
            products_data[p] = {
                "dates": [d.strftime("%Y-%m-%d") for d in sv.index],
                "values": [round(v, 2) for v in sv.values],
                "total": round(float(totals_p[p]), 2),
            }
        results["exports_by_product"] = products_data
    except Exception as ex:
        results["exports_by_product"] = {"error": str(ex)}

    # 2. Exports by destination country
    try:
        df_dest = _kpler_flows_client.get(
            flow_direction=[FlowsDirection.Export],
            split=[FlowsSplit.DestinationCountries],
            granularity=[FlowsPeriod.Monthly],
            unit=[FlowsMeasurementUnit.KBD],
            start_date=sd, end_date=ed,
            from_installations=[installation],
            with_forecast=False,
        )
        long_dest = _kpler_melt(df_dest, var_name="country")
        long_dest = long_dest[long_dest["country"] != "Total"].dropna(subset=["value"])
        pivot_d = long_dest.pivot_table(index="date", columns="country", values="value", aggfunc="sum").round(2).fillna(0)
        totals_d = pivot_d.sum().sort_values(ascending=False)
        total_all = float(totals_d.sum())
        destinations_data = {}
        for c in list(totals_d.head(20).index):
            sv = pivot_d[c]
            destinations_data[c] = {
                "dates": [d.strftime("%Y-%m-%d") for d in sv.index],
                "values": [round(v, 2) for v in sv.values],
                "total": round(float(totals_d[c]), 2),
                "share_pct": round(float(totals_d[c]) / total_all * 100, 1) if total_all > 0 else 0,
            }
        results["exports_by_destination"] = destinations_data
    except Exception as ex:
        results["exports_by_destination"] = {"error": str(ex)}

    # 3. Imports by product (what the refinery receives)
    try:
        df_imp = _kpler_flows_client.get(
            flow_direction=[FlowsDirection.Import],
            split=[FlowsSplit.Products],
            granularity=[FlowsPeriod.Monthly],
            unit=[FlowsMeasurementUnit.KBD],
            start_date=sd, end_date=ed,
            to_installations=[installation],
            with_forecast=False,
        )
        long_imp = _kpler_melt(df_imp, var_name="product")
        long_imp = long_imp[long_imp["product"] != "Total"].dropna(subset=["value"])
        pivot_i = long_imp.pivot_table(index="date", columns="product", values="value", aggfunc="sum").round(2).fillna(0)
        totals_i = pivot_i.sum().sort_values(ascending=False)
        imports_data = {}
        for p in totals_i.index:
            sv = pivot_i[p]
            imports_data[p] = {
                "dates": [d.strftime("%Y-%m-%d") for d in sv.index],
                "values": [round(v, 2) for v in sv.values],
                "total": round(float(totals_i[p]), 2),
            }
        results["imports_by_product"] = imports_data
    except Exception as ex:
        results["imports_by_product"] = {"error": str(ex)}

    # 4. Imports by origin country (where crude/feedstock comes from)
    try:
        df_orig = _kpler_flows_client.get(
            flow_direction=[FlowsDirection.Import],
            split=[FlowsSplit.OriginCountries],
            granularity=[FlowsPeriod.Monthly],
            unit=[FlowsMeasurementUnit.KBD],
            start_date=sd, end_date=ed,
            to_installations=[installation],
            with_forecast=False,
        )
        long_orig = _kpler_melt(df_orig, var_name="country")
        long_orig = long_orig[long_orig["country"] != "Total"].dropna(subset=["value"])
        pivot_o = long_orig.pivot_table(index="date", columns="country", values="value", aggfunc="sum").round(2).fillna(0)
        totals_o = pivot_o.sum().sort_values(ascending=False)
        total_imp_all = float(totals_o.sum())
        origins_data = {}
        for c in list(totals_o.head(20).index):
            sv = pivot_o[c]
            origins_data[c] = {
                "dates": [d.strftime("%Y-%m-%d") for d in sv.index],
                "values": [round(v, 2) for v in sv.values],
                "total": round(float(totals_o[c]), 2),
                "share_pct": round(float(totals_o[c]) / total_imp_all * 100, 1) if total_imp_all > 0 else 0,
            }
        results["imports_by_origin"] = origins_data
    except Exception as ex:
        results["imports_by_origin"] = {"error": str(ex)}

    return {"installation": installation, "data": results}


_kpler_inventories_client = None

def _ensure_kpler_inventories():
    """Lazy-load Kpler Inventories client."""
    global _kpler_inventories_client
    if _kpler_inventories_client is not None:
        return True
    if not _ensure_kpler():
        return False
    try:
        from kpler.sdk.resources.inventories import Inventories
        from kpler.sdk.resources.inventories_cushing_drone import InventoriesCushingDrone
        from kpler.sdk import Platform
        from kpler.sdk.configuration import Configuration
        username = os.environ.get("KPLER_USERNAME", "")
        password = os.environ.get("KPLER_PASSWORD", "")
        config = Configuration(Platform.Liquids, username, password)
        _kpler_inventories_client = Inventories(config)
        return True
    except Exception as e:
        print(f"KPLER Inventories init failed: {e}")
        return False


@app.get("/api/kpler/inventories")
async def get_kpler_inventories(
    zone: str = "United States",
    period: str = "weekly",
    split: str = "total",
    start_date: str = "2025-01-01",
    end_date: str = "2026-12-31",
):
    """Get Kpler satellite-based crude oil inventory data."""
    if not _ensure_kpler_inventories():
        raise HTTPException(status_code=503, detail="Kpler Inventories not available.")

    from kpler.sdk import InventoriesPeriod, InventoriesSplit
    from datetime import date as dt_date

    s = start_date.split("-")
    e = end_date.split("-")
    sd = dt_date(int(s[0]), int(s[1]), int(s[2]))
    ed = dt_date(int(e[0]), int(e[1]), int(e[2]))

    period_map = {
        "daily": InventoriesPeriod.Daily,
        "weekly": InventoriesPeriod.Weekly,
        "eia-weekly": InventoriesPeriod.EiaWeekly,
        "monthly": InventoriesPeriod.Monthly,
    }
    split_map = {
        "total": InventoriesSplit.Total,
        "byCountry": InventoriesSplit.ByCountry,
        "byInstallation": InventoriesSplit.ByInstallation,
    }

    try:
        df = _kpler_inventories_client.get(
            zones=[zone],
            period=period_map.get(period, InventoriesPeriod.Weekly),
            split=split_map.get(split, InventoriesSplit.Total),
            start_date=sd,
            end_date=ed,
        )
        if df is None or len(df) == 0:
            return {"zone": zone, "data": [], "error": "No data"}

        # For total split, return time series
        result_rows = []
        for _, row in df.iterrows():
            r = {
                "date": str(row.get("Date", "")),
                "level_kb": round(float(row.get("Level (kb)", 0)), 1),
                "capacity_kb": round(float(row.get("Capacity (kb)", 0)), 1),
                "fill_pct": round(float(row.get("Relative Fill Level", 0)) * 100, 1),
                "local_supply_kbd": round(float(row.get("Local Supply (kbd)", 0)), 1),
                "local_demand_kbd": round(float(row.get("Local Demand (kbd)", 0)), 1),
                "cargoes_kbd": round(float(row.get("Cargoes (kbd)", 0)), 1),
            }
            result_rows.append(r)

        # If byInstallation or byCountry, also parse the wide columns
        breakdown = {}
        skip_cols = {"Date", "Zone", "Installation", "Level (kb)", "Local Supply (kbd)",
                     "Local Demand (kbd)", "Cargoes (kbd)", "Capacity (kb)",
                     "Relative Fill Level", "Country", "Continent", "Revisit Rate",
                     "Last Image", "Delta level (kb)", "EIA adjustment level (kb)",
                     "EIA adjustment capacity (kb)", "Period End Date"}
        extra_cols = [c for c in df.columns if c not in skip_cols]
        if extra_cols and split != "total":
            for col in extra_cols[:30]:
                vals = df[col].fillna(0).tolist()
                breakdown[col] = {
                    "values": [round(float(v), 1) for v in vals],
                    "latest": round(float(vals[-1]) if vals else 0, 1),
                    "total": round(sum(float(v) for v in vals), 1),
                }

        return {
            "zone": zone,
            "period": period,
            "split": split,
            "dates": [str(row.get("Date", "")) for _, row in df.iterrows()],
            "data": result_rows,
            "breakdown": breakdown,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/kpler/inventories_multi")
async def get_kpler_inventories_multi(
    zones: str = "United States,China,Singapore Republic,Greater ARA,Japan,India,South Korea,Fujairah",
    period: str = "weekly",
    start_date: str = "2025-01-01",
    end_date: str = "2026-12-31",
):
    """Get inventories for multiple zones at once for comparison."""
    if not _ensure_kpler_inventories():
        raise HTTPException(status_code=503, detail="Kpler Inventories not available.")

    from kpler.sdk import InventoriesPeriod, InventoriesSplit
    from datetime import date as dt_date

    s = start_date.split("-")
    e = end_date.split("-")
    sd = dt_date(int(s[0]), int(s[1]), int(s[2]))
    ed = dt_date(int(e[0]), int(e[1]), int(e[2]))

    period_map = {
        "daily": InventoriesPeriod.Daily,
        "weekly": InventoriesPeriod.Weekly,
        "monthly": InventoriesPeriod.Monthly,
    }

    zone_list = [z.strip() for z in zones.split(",") if z.strip()]
    results = {}
    for zone in zone_list:
        try:
            df = _kpler_inventories_client.get(
                zones=[zone],
                period=period_map.get(period, InventoriesPeriod.Weekly),
                split=InventoriesSplit.Total,
                start_date=sd,
                end_date=ed,
            )
            if df is not None and len(df) > 0:
                dates = [str(row.get("Date", "")) for _, row in df.iterrows()]
                levels = [round(float(row.get("Level (kb)", 0)), 1) for _, row in df.iterrows()]
                caps = [round(float(row.get("Capacity (kb)", 0)), 1) for _, row in df.iterrows()]
                fills = [round(float(row.get("Relative Fill Level", 0)) * 100, 1) for _, row in df.iterrows()]
                results[zone] = {
                    "dates": dates,
                    "levels": levels,
                    "capacities": caps,
                    "fill_pcts": fills,
                    "latest_level": levels[-1] if levels else 0,
                    "latest_capacity": caps[-1] if caps else 0,
                    "latest_fill": fills[-1] if fills else 0,
                }
        except Exception:
            pass

    return {"zones": results}


@app.get("/api/kpler/cushing_drone")
async def get_kpler_cushing_drone(
    start_date: str = "2025-01-01",
    end_date: str = "2026-12-31",
):
    """Get high-frequency Cushing drone inventory data."""
    if not _ensure_kpler():
        raise HTTPException(status_code=503, detail="Kpler SDK not available.")
    try:
        from kpler.sdk.resources.inventories_cushing_drone import InventoriesCushingDrone
        from kpler.sdk import Platform
        from kpler.sdk.configuration import Configuration
        from datetime import date as dt_date

        username = os.environ.get("KPLER_USERNAME", "")
        password = os.environ.get("KPLER_PASSWORD", "")
        config = Configuration(Platform.Liquids, username, password)
        cushing = InventoriesCushingDrone(config)

        s = start_date.split("-")
        e = end_date.split("-")
        sd = dt_date(int(s[0]), int(s[1]), int(s[2]))
        ed = dt_date(int(e[0]), int(e[1]), int(e[2]))

        df = cushing.get(start_date=sd, end_date=ed)
        if df is None or len(df) == 0:
            return {"data": []}

        data = []
        for _, row in df.iterrows():
            data.append({
                "date": str(row.get("Date", "")),
                "level_kb": round(float(row.get("Level (kb)", 0)), 1),
                "capacity_kb": round(float(row.get("Capacity (kb)", 0)), 1),
                "utilization": round(float(row.get("capacity_utilization", 0)) * 100, 1),
            })
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Genscape Refinery Runs (Offline Capacity) + Pipeline Flows
# ---------------------------------------------------------------------------
_GENSCAPE_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "genscape")
_genscape_monthly_df = None
_genscape_daily_df = None
_genscape_last_pulled = None  # ISO timestamp of last API refresh

# Map unitCategory → alternativeCategory (short code used in tables/charts)
_UNIT_CAT_MAP = {
    "Atmospheric Crude Distillation": "CDU",
    "Vacuum Crude Distillation": "VDU",
    "Fluid Catalytic Cracker": "FCC",
    "Hydrocracker": "HCU",
    "Coker": "COK",
    "Reformer": "RFM",
    "Isomerization": "ISO",
    "Alkylation": "ALK",
    "Aromatics": "ARO",
    "Polymerization": "POL",
    "Cogeneration": "COG",
    "Sulfur": "SUL",
}

def _map_alt_category(cat: str) -> str:
    if cat in _UNIT_CAT_MAP:
        return _UNIT_CAT_MAP[cat]
    if cat and "hydrotreater" in cat.lower():
        return "HT"
    return cat or "OTHER"

def _derive_monthly_from_daily():
    """Aggregate the daily unit-status data to a monthly frame when no
    pre-computed monthly parquet exists (e.g. fresh API-bootstrapped deploys)."""
    daily = _load_genscape_daily()
    if daily is None or daily.empty:
        return None
    d = daily.copy()
    d["offlineValue"] = np.where(d["unitOnline"] == False, d["unitCapacity"], 0.0)  # noqa: E712
    d["monthDate"] = d["measurementDate"].values.astype("datetime64[M]")
    agg = (
        d.groupby(["monthDate", "unitId"])
        .agg(
            offlineValue=("offlineValue", "mean"),
            unitCapacity=("unitCapacity", "max"),
            facilityName=("facilityName", "first"),
            unitName=("unitName", "first"),
            region=("region", "first"),
            alternativeCategory=("alternativeCategory", "first"),
        )
        .reset_index()
    )
    return agg


def _load_genscape_monthly():
    global _genscape_monthly_df
    if _genscape_monthly_df is not None:
        return _genscape_monthly_df
    path = os.path.join(_GENSCAPE_DATA_DIR, "runs_status_monthly.parquet")
    if not os.path.isfile(path):
        df = _derive_monthly_from_daily()
        if df is None:
            return None
        df["monthDate"] = pd.to_datetime(df["monthDate"])
        df["month"] = df["monthDate"].dt.month
        df["year"] = df["monthDate"].dt.year
        _genscape_monthly_df = df
        return df
    df = pd.read_parquet(path)
    df["monthDate"] = pd.to_datetime(df["monthDate"])
    df["month"] = df["monthDate"].dt.month
    df["year"] = df["monthDate"].dt.year
    df["offlineValue"] = df["offlineValue"].fillna(0)
    df["unitCapacity"] = df["unitCapacity"].fillna(0)
    _genscape_monthly_df = df
    return df

_genscape_bootstrap_attempted = False


def _load_genscape_daily():
    global _genscape_daily_df, _genscape_bootstrap_attempted
    if _genscape_daily_df is not None:
        return _genscape_daily_df
    path = os.path.join(_GENSCAPE_DATA_DIR, "runs_status.parquet")
    if not os.path.isfile(path):
        # No historical file (e.g. fresh deployment) — bootstrap from the API once
        if not _genscape_bootstrap_attempted and os.environ.get("GSPE_API_KEY"):
            _genscape_bootstrap_attempted = True
            try:
                _genscape_pull_and_merge(lookback_days=365)
            except Exception as exc:
                print(f"[GSPE-Bootstrap] failed: {exc}")
    if not os.path.isfile(path):
        return None
    df = pd.read_parquet(path)
    df["measurementDate"] = pd.to_datetime(df["measurementDate"])
    _genscape_daily_df = df
    # Set last_pulled from file modification time
    global _genscape_last_pulled
    if _genscape_last_pulled is None:
        import datetime as _dt
        mtime = os.path.getmtime(path)
        _genscape_last_pulled = _dt.datetime.fromtimestamp(mtime, tz=_dt.timezone.utc).isoformat()
    return df


_GSPE_API_REGION_MAP = {
    "East Coast": "PADD1",
    "Mid-Continent": "PADD2",
    "Gulf Coast": "PADD3",
    "West US": "PADD5",
    "Canada": "Canada",
}

def _genscape_pull_and_merge(lookback_days: int = 3) -> dict:
    """Pull last N days from Genscape API, merge with existing data using keep=first dedup."""
    import http.client
    import json as json_mod
    from datetime import datetime as _dt, timedelta, timezone

    global _genscape_daily_df, _genscape_last_pulled

    api_key = os.environ.get("GSPE_API_KEY", "")
    if not api_key:
        return {"error": "GSPE_API_KEY not configured"}

    # API only covers North American regions (PADD1-5, Canada); Europe/UK come from historical bulk data
    api_regions = {"PADD1", "PADD2", "PADD3", "PADD4", "PADD5", "Canada"}
    existing = _load_genscape_daily()
    if existing is not None and not existing.empty:
        # Only consider API-accessible regions for refresh start date
        api_data = existing[existing["region"].isin(api_regions)]
        if not api_data.empty:
            max_date = api_data["measurementDate"].max()
        else:
            max_date = existing["measurementDate"].max()
        start_date = (max_date - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        print(f"[GSPE-Refresh] API region max: {max_date.date()}, start_date={start_date}")
    else:
        start_date = (_dt.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    end_date = (_dt.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Pull all pages from API
    all_rows = []
    offset = 0
    limit = 5000
    while True:
        conn = http.client.HTTPSConnection("api.genscape.com")
        url = f"/refineries/oil/v2/unit-status/daily?startDate={start_date}&endDate={end_date}&limit={limit}&offset={offset}&format=json"
        conn.request("GET", url, "{}", {"Gen-Api-Key": api_key})
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        if resp.status != 200:
            return {"error": f"API returned {resp.status}"}
        data = json_mod.loads(raw)
        rows = data.get("data", [])
        all_rows.extend(rows)
        if len(rows) < limit:
            break
        offset += limit

    if not all_rows:
        return {"error": "No new data returned from API", "start_date": start_date, "end_date": end_date}

    # Build DataFrame from API response
    new_df = pd.DataFrame(all_rows)
    new_df["measurementDate"] = pd.to_datetime(new_df["measurementDate"])
    new_df["unitCapacity"] = pd.to_numeric(new_df.get("unitCapacity", 0), errors="coerce").fillna(0)
    # API returns capacity in bpd, existing data is in kbd — check and convert
    if new_df["unitCapacity"].median() > 1000:
        new_df["unitCapacity"] = new_df["unitCapacity"] / 1000.0
    # Map alternativeCategory from unitCategory
    new_df["alternativeCategory"] = new_df["unitCategory"].apply(_map_alt_category)
    # Map API region names to PADD names: use existing unitId→region mapping first,
    # then fallback to API region name mapping (API "West US" covers both PADD4+PADD5)
    if existing is not None and not existing.empty:
        unit_region_map = existing.drop_duplicates("unitId").set_index("unitId")["region"].to_dict()
        new_df["region"] = new_df.apply(
            lambda r: unit_region_map.get(r["unitId"], _GSPE_API_REGION_MAP.get(r["region"], r["region"])),
            axis=1,
        )
    else:
        new_df["region"] = new_df["region"].map(lambda r: _GSPE_API_REGION_MAP.get(r, r))

    # Merge with existing data — keep=first (existing records take priority over revisions)
    path = os.path.join(_GENSCAPE_DATA_DIR, "runs_status.parquet")
    if existing is not None and not existing.empty:
        # Ensure consistent columns
        common_cols = [c for c in existing.columns if c in new_df.columns]
        combined = pd.concat([existing[common_cols], new_df[common_cols]], ignore_index=True)
        # Dedup: keep=first means existing (original) data wins over new (revised) data
        combined = combined.drop_duplicates(subset=["measurementDate", "unitId"], keep="first")
        combined = combined.sort_values("measurementDate").reset_index(drop=True)
    else:
        combined = new_df

    # Save back to parquet
    os.makedirs(_GENSCAPE_DATA_DIR, exist_ok=True)
    combined.to_parquet(path, index=False)

    # Reset cached DataFrames so next load picks up new data
    _genscape_daily_df = None
    global _genscape_monthly_df
    _genscape_monthly_df = None
    now_ts = _dt.now(timezone.utc).isoformat()
    _genscape_last_pulled = now_ts

    new_dates = sorted(new_df["measurementDate"].dt.strftime("%Y-%m-%d").unique())
    return {
        "status": "ok",
        "pulled_from": start_date,
        "pulled_to": end_date,
        "new_records": len(all_rows),
        "total_records": len(combined),
        "new_dates": new_dates,
        "dedup_strategy": "keep=first (existing data preserved over revisions)",
        "last_pulled": now_ts,
    }


@app.post("/api/genscape/refresh")
async def genscape_refresh_data(lookback_days: int = Query(3)):
    """Pull latest N days from Genscape API, merge with keep=first dedup (preserves original data over revisions)."""
    result = _genscape_pull_and_merge(lookback_days=lookback_days)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    # Also sync to Azure SQL if configured
    if _DB_AVAILABLE and is_db_enabled():
        try:
            df = _load_genscape_daily()
            if df is not None and not df.empty:
                recent = df[df["measurementDate"] >= (pd.Timestamp.now() - pd.Timedelta(days=lookback_days))]
                _db_refresh_genscape_us(recent.to_dict(orient="records"))
                result["db_synced"] = True
        except Exception as e:
            result["db_sync_error"] = str(e)
    return result


@app.post("/api/genscape/refresh_europe")
async def genscape_refresh_europe(lookback_days: int = Query(3)):
    """Pull latest Europe+UK data using European API key, merge with keep=first dedup."""
    import http.client
    import json as json_mod
    import urllib.parse
    from datetime import datetime as _dt, timedelta, timezone

    global _genscape_daily_df, _genscape_last_pulled

    eu_api_key = os.environ.get("GSPE_EU_API_KEY", "")
    if not eu_api_key:
        raise HTTPException(status_code=500, detail="GSPE_EU_API_KEY not configured")

    existing = _load_genscape_daily()
    eu_regions = {"Europe", "United Kingdom"}
    if existing is not None and not existing.empty:
        eu_data = existing[existing["region"].isin(eu_regions)]
        max_date = eu_data["measurementDate"].max() if not eu_data.empty else existing["measurementDate"].max()
        start_date = (max_date - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    else:
        start_date = (_dt.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end_date = (_dt.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    all_rows = []
    offset = 0
    limit = 5000
    while True:
        conn = http.client.HTTPSConnection("api.genscape.com")
        params = urllib.parse.urlencode({
            "startDate": start_date, "endDate": end_date,
            "limit": limit, "offset": offset, "format": "json"
        })
        url = f"/refineries/oil/v2/unit-status/daily?{params}"
        conn.request("GET", url, headers={"Gen-Api-Key": eu_api_key})
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        if resp.status != 200:
            break
        data = json_mod.loads(raw)
        rows = data.get("data", [])
        all_rows.extend(rows)
        if len(rows) < limit:
            break
        offset += limit

    if not all_rows:
        raise HTTPException(status_code=500, detail=f"No data returned ({start_date} to {end_date})")

    new_df = pd.DataFrame(all_rows)
    new_df["measurementDate"] = pd.to_datetime(new_df["measurementDate"])
    new_df["unitCapacity"] = pd.to_numeric(new_df.get("unitCapacity", 0), errors="coerce").fillna(0)
    if new_df["unitCapacity"].median() > 1000:
        new_df["unitCapacity"] = new_df["unitCapacity"] / 1000.0
    new_df["alternativeCategory"] = new_df["unitCategory"].apply(_map_alt_category)

    # Only keep Europe + United Kingdom rows from the pull
    new_eu = new_df[new_df["region"].isin(eu_regions)].copy()

    # Merge with existing
    path = os.path.join(_GENSCAPE_DATA_DIR, "runs_status.parquet")
    if existing is not None and not existing.empty:
        common_cols = [c for c in existing.columns if c in new_eu.columns]
        combined = pd.concat([existing[common_cols], new_eu[common_cols]], ignore_index=True)
        combined = combined.drop_duplicates(subset=["measurementDate", "unitId"], keep="first")
        combined = combined.sort_values("measurementDate").reset_index(drop=True)
    else:
        combined = new_eu

    combined.to_parquet(path, index=False)
    _genscape_daily_df = None
    now_ts = _dt.now(timezone.utc).isoformat()
    _genscape_last_pulled = now_ts

    eu_new = len(new_eu)
    result = {
        "status": "ok", "pulled_from": start_date, "pulled_to": end_date,
        "new_records": eu_new, "total_records": len(combined),
        "last_pulled": now_ts,
    }
    # Also sync to Azure SQL if configured
    if _DB_AVAILABLE and is_db_enabled():
        try:
            _db_refresh_genscape_eu(new_eu.to_dict(orient="records"))
            result["db_synced"] = True
        except Exception as e:
            result["db_sync_error"] = str(e)
    return result


@app.get("/api/genscape/last_pulled")
async def genscape_last_pulled():
    """Return the timestamp of the last data refresh."""
    _load_genscape_daily()  # ensure _genscape_last_pulled is set from file mtime
    return {"last_pulled": _genscape_last_pulled}


@app.get("/api/genscape/regions")
async def genscape_regions():
    df = _load_genscape_monthly()
    if df is None:
        raise HTTPException(status_code=404, detail="Genscape data not available")
    regions = sorted(df["region"].dropna().unique().tolist())
    return {"regions": regions}


@app.get("/api/genscape/categories")
async def genscape_categories():
    df = _load_genscape_monthly()
    if df is None:
        raise HTTPException(status_code=404, detail="Genscape data not available")
    cats = sorted(df["alternativeCategory"].dropna().unique().tolist())
    return {"categories": cats}


@app.get("/api/genscape/offline_capacity")
async def genscape_offline_capacity(
    region: str = Query(None),
    category: str = Query(None),
    start_year: int = Query(2015),
    end_year: int = Query(2026),
):
    """Monthly offline capacity aggregated by region/category with seasonal overlays."""
    df = _load_genscape_monthly()
    if df is None:
        raise HTTPException(status_code=404, detail="Genscape data not available")

    filt = df[(df["year"] >= start_year) & (df["year"] <= end_year)].copy()

    # Exclude permanently shut facilities and Idled outage types from offline counts
    if "facilityName" in filt.columns:
        filt = filt[~filt["facilityName"].isin(_GSPE_EXCLUDED_FACILITIES)]
        filt = filt[~filt["facilityName"].isin(_GSPE_CANADIAN_IN_PADD)]

    if region and region != "All":
        if region == "US Total":
            filt = filt[filt["region"].str.startswith("PADD")]
        else:
            filt = filt[filt["region"] == region]

    if category and category != "All":
        filt = filt[filt["alternativeCategory"] == category]

    # --- Total offline by month ---
    total_by_month = (
        filt.groupby("monthDate")["offlineValue"]
        .sum()
        .reset_index()
        .sort_values("monthDate")
    )
    total_series = {
        "dates": total_by_month["monthDate"].dt.strftime("%Y-%m-%d").tolist(),
        "values": total_by_month["offlineValue"].round(1).tolist(),
    }

    # --- Total capacity by month (for utilization) ---
    total_cap_by_month = (
        filt.groupby("monthDate")["unitCapacity"]
        .sum()
        .reset_index()
        .sort_values("monthDate")
    )
    capacity_series = {
        "dates": total_cap_by_month["monthDate"].dt.strftime("%Y-%m-%d").tolist(),
        "values": total_cap_by_month["unitCapacity"].round(1).tolist(),
    }

    # --- By category (stacked area) ---
    by_cat = (
        filt.groupby(["monthDate", "alternativeCategory"])["offlineValue"]
        .sum()
        .reset_index()
    )
    cat_series = {}
    for cat in sorted(by_cat["alternativeCategory"].unique()):
        sub = by_cat[by_cat["alternativeCategory"] == cat].sort_values("monthDate")
        cat_series[cat] = {
            "dates": sub["monthDate"].dt.strftime("%Y-%m-%d").tolist(),
            "values": sub["offlineValue"].round(1).tolist(),
        }

    # --- By region ---
    by_region = (
        filt.groupby(["monthDate", "region"])["offlineValue"]
        .sum()
        .reset_index()
    )
    region_series = {}
    for r in sorted(by_region["region"].unique()):
        sub = by_region[by_region["region"] == r].sort_values("monthDate")
        region_series[r] = {
            "dates": sub["monthDate"].dt.strftime("%Y-%m-%d").tolist(),
            "values": sub["offlineValue"].round(1).tolist(),
        }

    # --- Seasonal overlay (multi-year, month 1-12) ---
    filt_seas = filt.copy()
    filt_seas["month"] = filt_seas["monthDate"].dt.month
    filt_seas["year"] = filt_seas["monthDate"].dt.year
    monthly_totals = filt_seas.groupby(["year", "month"])["offlineValue"].sum().reset_index()
    seasonal = {}
    for yr in sorted(monthly_totals["year"].unique()):
        yr_data = monthly_totals[monthly_totals["year"] == yr].sort_values("month")
        seasonal[int(yr)] = {
            "months": yr_data["month"].tolist(),
            "values": yr_data["offlineValue"].round(1).tolist(),
        }

    # --- 5-year average + range (2015-2019) ---
    hist = monthly_totals[(monthly_totals["year"] >= 2015) & (monthly_totals["year"] <= 2019)]
    if not hist.empty:
        avg_by_month = hist.groupby("month")["offlineValue"].agg(["mean", "min", "max"]).reset_index()
        avg_5y = {
            "months": avg_by_month["month"].tolist(),
            "avg": avg_by_month["mean"].round(1).tolist(),
            "min": avg_by_month["min"].round(1).tolist(),
            "max": avg_by_month["max"].round(1).tolist(),
        }
    else:
        avg_5y = None

    # --- Latest month summary table ---
    latest_month = filt["monthDate"].max()
    latest = filt[filt["monthDate"] == latest_month]
    summary_by_cat = (
        latest.groupby("alternativeCategory")
        .agg(offline=("offlineValue", "sum"), capacity=("unitCapacity", "sum"), units=("unitId", "nunique"))
        .reset_index()
        .sort_values("offline", ascending=False)
    )
    summary_by_cat["pct_offline"] = (summary_by_cat["offline"] / summary_by_cat["capacity"].replace(0, np.nan) * 100).fillna(0).round(1)
    summary_table = summary_by_cat.to_dict(orient="records")

    summary_by_region = (
        latest.groupby("region")
        .agg(offline=("offlineValue", "sum"), capacity=("unitCapacity", "sum"), units=("unitId", "nunique"))
        .reset_index()
        .sort_values("offline", ascending=False)
    )
    summary_by_region["pct_offline"] = (summary_by_region["offline"] / summary_by_region["capacity"].replace(0, np.nan) * 100).fillna(0).round(1)
    region_table = summary_by_region.to_dict(orient="records")

    return {
        "total_series": total_series,
        "capacity_series": capacity_series,
        "by_category": cat_series,
        "by_region": region_series,
        "seasonal": seasonal,
        "avg_5y": avg_5y,
        "summary_by_category": summary_table,
        "summary_by_region": region_table,
        "latest_month": latest_month.strftime("%Y-%m-%d") if latest_month is not None else None,
        "selected_region": region or "All",
        "selected_category": category or "All",
    }


@app.get("/api/genscape/facilities")
async def genscape_facilities(
    region: str = Query(None),
    category: str = Query(None),
):
    """Facility-level offline capacity for the latest month."""
    df = _load_genscape_monthly()
    if df is None:
        raise HTTPException(status_code=404, detail="Genscape data not available")

    latest_month = df["monthDate"].max()
    filt = df[df["monthDate"] == latest_month].copy()

    if region and region != "All":
        if region == "US Total":
            filt = filt[filt["region"].str.startswith("PADD")]
        else:
            filt = filt[filt["region"] == region]

    if category and category != "All":
        filt = filt[filt["alternativeCategory"] == category]

    by_facility = (
        filt.groupby(["facilityName", "region"])
        .agg(
            offline=("offlineValue", "sum"),
            capacity=("unitCapacity", "sum"),
            units_offline=("offlineValue", lambda x: (x > 0).sum()),
            total_units=("unitId", "nunique"),
        )
        .reset_index()
        .sort_values("offline", ascending=False)
    )
    by_facility["pct_offline"] = (by_facility["offline"] / by_facility["capacity"].replace(0, np.nan) * 100).fillna(0).round(1)
    by_facility = by_facility.head(50)

    return {
        "latest_month": latest_month.strftime("%Y-%m-%d"),
        "facilities": by_facility.to_dict(orient="records"),
    }


@app.get("/api/genscape/facility_detail")
async def genscape_facility_detail(
    facility: str = Query(...),
    start_year: int = Query(2020),
    end_year: int = Query(2026),
):
    """Unit-level time series for a specific facility."""
    df = _load_genscape_monthly()
    if df is None:
        raise HTTPException(status_code=404, detail="Genscape data not available")

    filt = df[
        (df["facilityName"] == facility)
        & (df["year"] >= start_year)
        & (df["year"] <= end_year)
    ].copy()

    if filt.empty:
        return {"facility": facility, "units": {}}

    units_data = {}
    for uid in filt["unitId"].unique():
        u = filt[filt["unitId"] == uid].sort_values("monthDate")
        unit_name = u["unitName"].iloc[0]
        cat = u["alternativeCategory"].iloc[0]
        cap = float(u["unitCapacity"].iloc[0])
        units_data[uid] = {
            "unitName": unit_name,
            "category": cat,
            "capacity": cap,
            "dates": u["monthDate"].dt.strftime("%Y-%m-%d").tolist(),
            "offlineValues": u["offlineValue"].round(1).tolist(),
        }

    return {"facility": facility, "units": units_data}


@app.get("/api/genscape/europe_analytics")
async def genscape_europe_analytics():
    """Return Europe + UK analytics: offline capacity by country, category, facility."""
    from datetime import timedelta
    df = _load_genscape_daily()
    if df is None:
        raise HTTPException(status_code=404, detail="Genscape daily data not available")

    eu = df[df["region"].isin(["Europe", "United Kingdom"])].copy()
    if eu.empty:
        raise HTTPException(status_code=404, detail="No Europe/UK data")

    eu["measurementDate"] = pd.to_datetime(eu["measurementDate"])
    latest_date = eu["measurementDate"].max()
    min_date = eu["measurementDate"].min()
    offline = eu[eu["unitOnline"] == False]

    # Date range
    date_range = {"min": min_date.strftime("%Y-%m-%d"), "max": latest_date.strftime("%Y-%m-%d")}

    # Unique countries and facilities
    countries = sorted(eu["region"].unique().tolist())
    eu_facs = sorted(eu["facilityName"].unique().tolist())

    # --- Latest-day summary ---
    latest_off = offline[offline["measurementDate"] == latest_date]
    latest_by_country = {}
    for reg in countries:
        rc = latest_off[latest_off["region"] == reg]
        latest_by_country[reg] = round(float(rc["unitCapacity"].sum()), 1)

    latest_by_cat = {}
    for cat in latest_off["alternativeCategory"].unique():
        cc = latest_off[latest_off["alternativeCategory"] == cat]
        latest_by_cat[cat] = round(float(cc["unitCapacity"].sum()), 1)

    # --- Daily offline time series (last 180 days) ---
    cutoff = latest_date - timedelta(days=180)
    recent = offline[offline["measurementDate"] >= cutoff]
    daily_ts = recent.groupby("measurementDate")["unitCapacity"].sum().reset_index()
    daily_ts = daily_ts.sort_values("measurementDate")
    ts_dates = daily_ts["measurementDate"].dt.strftime("%Y-%m-%d").tolist()
    ts_vals = daily_ts["unitCapacity"].round(1).tolist()

    # Daily by country
    daily_by_country = {}
    for reg in countries:
        rc = recent[recent["region"] == reg].groupby("measurementDate")["unitCapacity"].sum().reset_index().sort_values("measurementDate")
        daily_by_country[reg] = {
            "dates": rc["measurementDate"].dt.strftime("%Y-%m-%d").tolist(),
            "values": rc["unitCapacity"].round(1).tolist(),
        }

    # Daily by category (top 6)
    top_cats = offline.groupby("alternativeCategory")["unitCapacity"].sum().nlargest(6).index.tolist()
    daily_by_cat = {}
    for cat in top_cats:
        cc = recent[recent["alternativeCategory"] == cat].groupby("measurementDate")["unitCapacity"].sum().reset_index().sort_values("measurementDate")
        daily_by_cat[cat] = {
            "dates": cc["measurementDate"].dt.strftime("%Y-%m-%d").tolist(),
            "values": cc["unitCapacity"].round(1).tolist(),
        }

    # --- Seasonal overlay (all years) ---
    offline_daily = offline.copy()
    offline_daily["year"] = offline_daily["measurementDate"].dt.year
    offline_daily["doy"] = offline_daily["measurementDate"].dt.dayofyear
    yearly = offline_daily.groupby(["year", "doy"])["unitCapacity"].sum().reset_index()
    seasonal = {}
    for yr in sorted(yearly["year"].unique()):
        yd = yearly[yearly["year"] == yr].sort_values("doy")
        seasonal[int(yr)] = {"doy": yd["doy"].tolist(), "values": yd["unitCapacity"].round(1).tolist()}

    # --- Facility-level latest offline ---
    fac_latest = latest_off.groupby(["facilityName", "region", "alternativeCategory", "unitName"]).agg(
        capacity=("unitCapacity", "first"),
        outageType=("outageType", "first"),
    ).reset_index()
    fac_latest = fac_latest.sort_values("capacity", ascending=False)
    facility_list = []
    for _, row in fac_latest.iterrows():
        facility_list.append({
            "facility": row["facilityName"],
            "country": row["region"],
            "category": row["alternativeCategory"],
            "unit": row["unitName"],
            "capacity": round(float(row["capacity"]), 1),
            "outageType": row["outageType"] if pd.notna(row["outageType"]) else "Unknown",
        })

    # --- Country facility counts ---
    country_stats = {}
    for reg in countries:
        rc = eu[eu["region"] == reg]
        country_stats[reg] = {
            "total_facilities": int(rc["facilityName"].nunique()),
            "total_units": int(rc["unitId"].nunique()),
            "latest_offline_kbd": latest_by_country.get(reg, 0),
        }

    return {
        "date_range": date_range,
        "countries": countries,
        "facilities": eu_facs,
        "country_stats": country_stats,
        "latest_by_country": latest_by_country,
        "latest_by_category": latest_by_cat,
        "daily_total": {"dates": ts_dates, "values": ts_vals},
        "daily_by_country": daily_by_country,
        "daily_by_category": daily_by_cat,
        "seasonal": seasonal,
        "facility_offline": facility_list,
    }


@app.get("/api/genscape/pipeline_flows")
async def genscape_pipeline_flows(
    frequency: str = Query("daily"),
    limit: int = Query(5000),
):
    """Fetch pipeline flows from Genscape API (Mid-Continent)."""
    import http.client
    import json as json_mod
    import urllib.parse

    api_key = os.environ.get("GSPE_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="GSPE_API_KEY not configured")

    base = f"/transportation/oil/v2/pipeline-flows/{frequency}?revision=revised"
    params = urllib.parse.urlencode({"limit": limit, "offset": 0, "format": "json"})
    url = f"{base}&{params}"

    conn = http.client.HTTPSConnection("api.genscape.com")
    conn.request("GET", url, "{body}", {"Gen-Api-Key": api_key})
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()

    if resp.status != 200:
        raise HTTPException(status_code=resp.status, detail="Genscape API error")

    data = json_mod.loads(raw)
    rows = data.get("data", [])

    if not rows:
        return {"pipelines": [], "summary": {}, "by_direction": {}}

    pdf = pd.DataFrame(rows)
    if "reportDate" in pdf.columns:
        pdf["reportDate"] = pd.to_datetime(pdf["reportDate"])

    latest_date = pdf["reportDate"].max()
    latest = pdf[pdf["reportDate"] == latest_date]

    by_dir = latest.groupby("direction").agg(
        total_flow=("flowBpd", "sum"),
        pipelines=("pipelineName", "nunique"),
    ).reset_index()

    cushing_in = float(latest[latest["direction"].str.contains("Cushing Incoming", na=False)]["flowBpd"].sum())
    cushing_out = float(latest[latest["direction"].str.contains("Cushing Outgoing", na=False)]["flowBpd"].sum())

    top_pipelines = (
        latest.sort_values("flowBpd", ascending=False)
        .head(20)[["pipelineName", "direction", "flowBpd", "pipelineCapacity", "startPumpStation", "finishPumpStation"]]
        .to_dict(orient="records")
    )

    # Time series for recent dates
    recent = pdf[pdf["reportDate"] >= (latest_date - pd.Timedelta(days=30))]
    daily_totals = recent.groupby("reportDate")["flowBpd"].sum().reset_index().sort_values("reportDate")
    daily_net = recent.copy()
    daily_net["is_incoming"] = daily_net["direction"].str.contains("Incoming", na=False)
    daily_in = daily_net[daily_net["is_incoming"]].groupby("reportDate")["flowBpd"].sum().reset_index()
    daily_in.columns = ["reportDate", "incoming"]
    daily_out = daily_net[~daily_net["is_incoming"]].groupby("reportDate")["flowBpd"].sum().reset_index()
    daily_out.columns = ["reportDate", "outgoing"]
    merged = daily_in.merge(daily_out, on="reportDate", how="outer").fillna(0).sort_values("reportDate")
    merged["net"] = merged["incoming"] - merged["outgoing"]

    return {
        "latest_date": latest_date.strftime("%Y-%m-%d"),
        "cushing_incoming": round(cushing_in),
        "cushing_outgoing": round(cushing_out),
        "cushing_net": round(cushing_in - cushing_out),
        "top_pipelines": top_pipelines,
        "by_direction": by_dir.to_dict(orient="records"),
        "daily_flows": {
            "dates": merged["reportDate"].dt.strftime("%Y-%m-%d").tolist(),
            "incoming": merged["incoming"].round(0).tolist(),
            "outgoing": merged["outgoing"].round(0).tolist(),
            "net": merged["net"].round(0).tolist(),
        },
    }


# --- Genscape 2-Week Offline Table (daily granularity, excl permanently idled) ---
# Facilities that are permanently shut/converting and should be excluded from offline tracking
_GSPE_EXCLUDED_FACILITIES = {
    "Lyondell - Houston",      # Permanently shut, converting to chemicals
    "Valero - Benicia",        # Converting to renewable diesel
    "Phillips 66 - Carson",    # Shut down
    "Phillips 66 - Wilmington", # Shut down
}

# Shell-Sarnia is physically in Canada but classified as PADD2; exclude from US totals
_GSPE_CANADIAN_IN_PADD = {"Shell - Sarnia"}


@app.get("/api/genscape/offline_table")
async def genscape_offline_table(days: int = Query(14), region: str = Query("US")):
    """2-week daily offline capacity table. region=US shows PADD breakdown; other values show facility-level for that region."""
    df = _load_genscape_daily()
    if df is None:
        raise HTTPException(status_code=404, detail="Genscape daily data not available")

    # Determine region filter
    is_us = region in ("US", "US Total", "All")
    if is_us:
        # US PADDs, exclude permanently shut and Canadian-in-PADD facilities
        filtered = df[
            (df["region"].str.startswith("PADD"))
            & (~df["facilityName"].isin(_GSPE_EXCLUDED_FACILITIES))
            & (~df["facilityName"].isin(_GSPE_CANADIAN_IN_PADD))
        ].copy()
        sub_regions = ["PADD1", "PADD2", "PADD3", "PADD4", "PADD5"]
        total_label = "US"
    elif region.startswith("PADD"):
        filtered = df[df["region"] == region].copy()
        sub_regions = []
        total_label = region
    else:
        # Non-US region (Canada, Europe, United Kingdom, etc.)
        filtered = df[df["region"] == region].copy()
        sub_regions = []
        total_label = region

    # Only offline units (unitOnline == False)
    offline = filtered[filtered["unitOnline"] == False]

    # Get latest N days
    all_dates = sorted(offline["measurementDate"].unique())
    if len(all_dates) == 0:
        return {"dates": [], "padd_totals": {}, "facility_details": {}, "region_mode": region, "is_us": is_us}

    latest_date = all_dates[-1]
    cutoff = latest_date - pd.Timedelta(days=days)
    recent = offline[offline["measurementDate"] > cutoff]
    dates = sorted(recent["measurementDate"].unique())
    date_strs = [d.strftime("%m/%d") for d in dates]

    # Detect available unit categories in the data
    all_cats = sorted(recent["alternativeCategory"].dropna().unique().tolist())
    major_cats = [c for c in ["CDU", "FCC", "HCU", "COK", "RFM", "VDU"] if c in all_cats]
    # Also include any other categories present in this region
    extra_cats = [c for c in all_cats if c not in major_cats]
    major_cats.extend(extra_cats)

    # Build totals table: {category: {region_key: [daily values]}}
    padd_totals = {}
    for cat in major_cats:
        padd_totals[cat] = {}
        cat_data = recent[recent["alternativeCategory"] == cat]
        # Total for selected region
        total_daily = cat_data.groupby("measurementDate")["unitCapacity"].sum()
        padd_totals[cat][total_label] = [round(float(total_daily.get(d, 0)), 0) for d in dates]
        # Sub-regions (only for US)
        for sr in sub_regions:
            sr_data = cat_data[cat_data["region"] == sr]
            sr_daily = sr_data.groupby("measurementDate")["unitCapacity"].sum()
            padd_totals[cat][sr] = [round(float(sr_daily.get(d, 0)), 0) for d in dates]

    # Compute weekly averages
    n = len(dates)
    wk1_dates = dates[:7] if n >= 7 else dates[:n//2]
    wk2_dates = dates[7:] if n >= 7 else dates[n//2:]

    weekly_avgs = {}
    for cat in major_cats:
        weekly_avgs[cat] = {}
        cat_data = recent[recent["alternativeCategory"] == cat]
        region_keys = [total_label] + sub_regions
        for region_key in region_keys:
            if region_key == total_label and sub_regions:
                r_data = cat_data
            elif region_key == total_label:
                r_data = cat_data
            else:
                r_data = cat_data[cat_data["region"] == region_key]
            r_daily = r_data.groupby("measurementDate")["unitCapacity"].sum()
            wk1_vals = [float(r_daily.get(d, 0)) for d in wk1_dates]
            wk2_vals = [float(r_daily.get(d, 0)) for d in wk2_dates]
            wk1_avg = round(sum(wk1_vals) / max(len(wk1_vals), 1), 0)
            wk2_avg = round(sum(wk2_vals) / max(len(wk2_vals), 1), 0)
            delta = round(wk2_avg - wk1_avg, 0)
            weekly_avgs[cat][region_key] = {"wk1": wk1_avg, "wk2": wk2_avg, "delta": delta}

    # Facility-level detail for ALL categories
    cat_labels = {
        "CDU": "Atmospheric Crude Distillation",
        "FCC": "Fluid Catalytic Cracker",
        "HCU": "Hydrocracker",
        "COK": "Coker",
        "RFM": "Reformer",
        "VDU": "Vacuum Distillation Unit",
        "HT": "Hydrotreater",
        "ALK": "Alkylation",
        "ISO": "Isomerization",
        "CBU": "Crude Blending Unit",
        "VBU": "Visbreaker",
        "ARO": "Aromatics",
        "ASP": "Asphalt",
        "GAS": "Gas Plant",
        "HGP": "Hydrogen Plant",
        "POW": "Power Generation",
        "SUL": "Sulfur Recovery",
    }
    facility_details = {}
    for cat in major_cats:
        cat_recent = recent[recent["alternativeCategory"] == cat]
        facilities = []
        if not cat_recent.empty:
            grouped = cat_recent.groupby(["facilityName", "unitName", "region"])
            for (fac, unit_name, reg), grp in grouped:
                cap = float(grp["unitCapacity"].iloc[0])
                daily_by_date = grp.set_index("measurementDate")["unitCapacity"]
                vals = [round(float(daily_by_date.get(d, 0)), 0) for d in dates]
                if any(v > 0 for v in vals):
                    wk1_v = [vals[i] for i in range(min(7, len(vals)))]
                    wk2_v = [vals[i] for i in range(min(7, len(vals)), len(vals))]
                    wk1_a = round(sum(wk1_v) / max(len(wk1_v), 1), 0) if wk1_v else 0
                    wk2_a = round(sum(wk2_v) / max(len(wk2_v), 1), 0) if wk2_v else 0
                    delta = round(wk2_a - wk1_a, 0)
                    facilities.append({
                        "facility": fac,
                        "unit": unit_name,
                        "region": reg,
                        "capacity": round(cap, 0),
                        "daily": vals,
                        "wk1": wk1_a,
                        "wk2": wk2_a,
                        "delta": delta,
                    })
        facilities.sort(key=lambda x: x["facility"] + x["unit"])
        facility_details[cat] = {
            "label": cat_labels.get(cat, cat),
            "facilities": facilities,
        }

    # MTD and MoM
    current_month = latest_date.replace(day=1)
    prior_month = (current_month - pd.Timedelta(days=1)).replace(day=1)
    mtd_stats = {}
    offline_for_mtd = filtered[filtered["unitOnline"] == False]
    for cat in major_cats:
        cat_all = offline_for_mtd[offline_for_mtd["alternativeCategory"] == cat]
        cur_month_data = cat_all[cat_all["measurementDate"] >= current_month]
        prior_month_data = cat_all[(cat_all["measurementDate"] >= prior_month) & (cat_all["measurementDate"] < current_month)]
        cur_avg = float(cur_month_data.groupby("measurementDate")["unitCapacity"].sum().mean()) if not cur_month_data.empty else 0
        prior_avg = float(prior_month_data.groupby("measurementDate")["unitCapacity"].sum().mean()) if not prior_month_data.empty else 0
        mtd_stats[cat] = {"mtd": round(cur_avg, 0), "mom": round(cur_avg - prior_avg, 0)}

        for fac_item in facility_details[cat]["facilities"]:
            fac_name, unit_name_val = fac_item["facility"], fac_item["unit"]
            fac_data = cat_all[(cat_all["facilityName"] == fac_name) & (cat_all["unitName"] == unit_name_val)]
            fac_cur = fac_data[fac_data["measurementDate"] >= current_month]
            fac_prior = fac_data[(fac_data["measurementDate"] >= prior_month) & (fac_data["measurementDate"] < current_month)]
            fac_mtd = round(float(fac_cur["unitCapacity"].mean()), 0) if not fac_cur.empty else 0
            fac_prior_avg = round(float(fac_prior["unitCapacity"].mean()), 0) if not fac_prior.empty else 0
            fac_item["mtd"] = fac_mtd
            fac_item["mom"] = round(fac_mtd - fac_prior_avg, 0)

    return {
        "dates": date_strs,
        "latest_date": latest_date.strftime("%Y-%m-%d"),
        "padd_totals": padd_totals,
        "weekly_avgs": weekly_avgs,
        "mtd_stats": mtd_stats,
        "facility_details": facility_details,
        "major_cats": major_cats,
        "padds": sub_regions,
        "region_mode": region,
        "is_us": is_us,
        "total_label": total_label,
    }


# --- Genscape Refinery Analytics (comprehensive) ---
@app.get("/api/genscape/refinery_analytics")
async def genscape_refinery_analytics():
    """Comprehensive refinery offline analytics: turnaround tracker, WoW changes, outage breakdown, PADD trends."""
    df = _load_genscape_daily()
    if df is None:
        raise HTTPException(status_code=404, detail="Genscape daily data not available")

    excl = _GSPE_EXCLUDED_FACILITIES | _GSPE_CANADIAN_IN_PADD
    us = df[(df["region"].str.startswith("PADD")) & (~df["facilityName"].isin(excl))].copy()
    offline = us[us["unitOnline"] == False]

    latest = us["measurementDate"].max()
    d30 = latest - pd.Timedelta(days=30)
    d90 = latest - pd.Timedelta(days=90)
    d365 = latest - pd.Timedelta(days=365)

    # 1. CDU Turnaround Tracker — daily CDU offline as % of US CDU capacity
    total_cdu_cap = float(us[us["alternativeCategory"] == "CDU"].drop_duplicates(subset=["facilityName", "unitName"])["unitCapacity"].sum())
    cdu_off = offline[offline["alternativeCategory"] == "CDU"]
    cdu_daily = cdu_off.groupby("measurementDate")["unitCapacity"].sum().reset_index()
    cdu_daily.columns = ["date", "offline"]
    cdu_daily["pct"] = round(cdu_daily["offline"] / total_cdu_cap * 100, 2) if total_cdu_cap > 0 else 0
    cdu_daily = cdu_daily.sort_values("date")

    turnaround = {
        "total_cdu_capacity": round(total_cdu_cap, 0),
        "dates": [d.strftime("%Y-%m-%d") for d in cdu_daily["date"]],
        "offline_kbd": [round(float(v), 0) for v in cdu_daily["offline"]],
        "pct_offline": [round(float(v), 2) for v in cdu_daily["pct"]],
    }

    # 2. Week-over-Week changes by category
    wk_now_start = latest - pd.Timedelta(days=6)
    wk_prev_start = latest - pd.Timedelta(days=13)
    wow = {}
    for cat in ["CDU", "FCC", "HCU", "COK", "RFM", "VDU"]:
        cat_off = offline[offline["alternativeCategory"] == cat]
        this_wk = cat_off[(cat_off["measurementDate"] >= wk_now_start) & (cat_off["measurementDate"] <= latest)]
        prev_wk = cat_off[(cat_off["measurementDate"] >= wk_prev_start) & (cat_off["measurementDate"] < wk_now_start)]
        this_avg = float(this_wk.groupby("measurementDate")["unitCapacity"].sum().mean()) if not this_wk.empty else 0
        prev_avg = float(prev_wk.groupby("measurementDate")["unitCapacity"].sum().mean()) if not prev_wk.empty else 0
        wow[cat] = {"this_week": round(this_avg, 0), "prev_week": round(prev_avg, 0), "change": round(this_avg - prev_avg, 0)}

    # 3. Outage type breakdown (latest day)
    latest_off = offline[offline["measurementDate"] == latest]
    outage_types = latest_off.groupby("outageType").agg(count=("unitCapacity", "count"), kbd=("unitCapacity", "sum")).reset_index()
    outage_breakdown = [{"type": str(r["outageType"]), "count": int(r["count"]), "kbd": round(float(r["kbd"]), 0)} for _, r in outage_types.iterrows()]

    # 4. PADD offline trends (last 90 days)
    padd_90 = offline[(offline["measurementDate"] >= d90) & (offline["alternativeCategory"] == "CDU")]
    padd_trends = {}
    for p in ["PADD1", "PADD2", "PADD3", "PADD4", "PADD5"]:
        p_data = padd_90[padd_90["region"] == p].groupby("measurementDate")["unitCapacity"].sum().reset_index()
        p_data = p_data.sort_values("measurementDate")
        padd_trends[p] = {
            "dates": [d.strftime("%Y-%m-%d") for d in p_data["measurementDate"]],
            "values": [round(float(v), 0) for v in p_data["unitCapacity"]],
        }

    # 5. Top offline facilities (latest day, all categories)
    top_fac = latest_off.groupby(["facilityName", "region"]).agg(
        offline_kbd=("unitCapacity", "sum"), units=("unitName", "count")
    ).reset_index().sort_values("offline_kbd", ascending=False).head(20)
    top_facilities = [{"facility": r["facilityName"], "region": r["region"],
                       "offline_kbd": round(float(r["offline_kbd"]), 0), "units": int(r["units"])}
                      for _, r in top_fac.iterrows()]

    # 6. Category offline time series (last 90 days)
    cat_ts = {}
    for cat in ["CDU", "FCC", "HCU", "COK", "RFM", "VDU"]:
        c_data = offline[(offline["alternativeCategory"] == cat) & (offline["measurementDate"] >= d90)]
        c_daily = c_data.groupby("measurementDate")["unitCapacity"].sum().reset_index().sort_values("measurementDate")
        cat_ts[cat] = {
            "dates": [d.strftime("%Y-%m-%d") for d in c_daily["measurementDate"]],
            "values": [round(float(v), 0) for v in c_daily["unitCapacity"]],
        }

    # 7. Units coming back online soon (were offline last 3 days, check transitions)
    last_3 = offline[offline["measurementDate"] >= latest - pd.Timedelta(days=2)]
    grp_last3 = last_3.groupby(["facilityName", "unitName"]).agg(
        days_offline=("measurementDate", "count"),
        region=("region", "first"),
        category=("alternativeCategory", "first"),
        capacity=("unitCapacity", "first"),
    ).reset_index()

    # 8. Monthly seasonal CDU offline (for multi-year overlay)
    monthly_df = _load_genscape_monthly()
    seasonal_cdu = {}
    if monthly_df is not None:
        us_monthly = monthly_df[(monthly_df["region"].str.startswith("PADD")) & (~monthly_df["facilityName"].isin(excl))]
        cdu_m = us_monthly[us_monthly["alternativeCategory"] == "CDU"]
        for yr in range(2020, 2027):
            yr_data = cdu_m[cdu_m["year"] == yr].groupby("month")["offlineValue"].sum().reset_index()
            if not yr_data.empty:
                seasonal_cdu[yr] = {
                    "months": [int(m) for m in yr_data["month"]],
                    "values": [round(float(v), 0) for v in yr_data["offlineValue"]],
                }
        # 5-year average (2016-2020)
        avg_data = cdu_m[cdu_m["year"].between(2016, 2020)].groupby("month")["offlineValue"].agg(["mean", "min", "max"]).reset_index()
        if not avg_data.empty:
            seasonal_cdu["avg_5y"] = {
                "months": [int(m) for m in avg_data["month"]],
                "avg": [round(float(v), 0) for v in avg_data["mean"]],
                "min": [round(float(v), 0) for v in avg_data["min"]],
                "max": [round(float(v), 0) for v in avg_data["max"]],
            }

    return {
        "latest_date": latest.strftime("%Y-%m-%d"),
        "turnaround_tracker": turnaround,
        "wow_changes": wow,
        "outage_breakdown": outage_breakdown,
        "padd_trends": padd_trends,
        "top_facilities": top_facilities,
        "category_timeseries": cat_ts,
        "seasonal_cdu": seasonal_cdu,
    }


@app.get("/api/genscape/briefing")
async def genscape_briefing():
    """Auto-generated trader briefing for Genscape refinery data."""
    df = _load_genscape_daily()
    if df is None:
        return {"bullets": ["Data not loaded. Click LOAD DATA to generate briefing."]}

    excl = _GSPE_EXCLUDED_FACILITIES | _GSPE_CANADIAN_IN_PADD
    us = df[(df["region"].str.startswith("PADD")) & (~df["facilityName"].isin(excl))].copy()
    offline = us[us["unitOnline"] == False]

    latest = us["measurementDate"].max()
    prev_day = latest - pd.Timedelta(days=1)
    prev_week = latest - pd.Timedelta(days=7)

    bullets = []
    highlights = []

    # Latest day totals
    latest_off = offline[offline["measurementDate"] == latest]
    total_offline_kbd = float(latest_off["unitCapacity"].sum())
    total_units_off = len(latest_off)

    # CDU specific
    cdu_off_today = latest_off[latest_off["alternativeCategory"] == "CDU"]
    cdu_kbd = float(cdu_off_today["unitCapacity"].sum())

    # Week-over-week by total
    wk_ago_off = offline[offline["measurementDate"] == prev_week]
    wk_ago_kbd = float(wk_ago_off["unitCapacity"].sum()) if not wk_ago_off.empty else total_offline_kbd
    wow_chg = total_offline_kbd - wk_ago_kbd
    wow_dir = "up" if wow_chg > 0 else "down"
    wow_pct = abs(wow_chg) / wk_ago_kbd * 100 if wk_ago_kbd > 0 else 0

    bullets.append(f"US total offline capacity: {total_offline_kbd:,.0f} kb/d across {total_units_off} units (as of {latest.strftime('%b %d')})")
    bullets.append(f"CDU offline: {cdu_kbd:,.0f} kb/d")
    if abs(wow_chg) > 10:
        bullets.append(f"Week-over-week total offline {wow_dir} {abs(wow_chg):,.0f} kb/d ({wow_pct:.1f}%)")

    # Category WoW changes
    cat_changes = []
    for cat in ["CDU", "FCC", "HCU", "COK", "VDU", "RFM"]:
        cat_today = float(latest_off[latest_off["alternativeCategory"] == cat]["unitCapacity"].sum())
        cat_wk = float(wk_ago_off[wk_ago_off["alternativeCategory"] == cat]["unitCapacity"].sum()) if not wk_ago_off.empty else cat_today
        chg = cat_today - cat_wk
        if abs(chg) > 20:
            direction = "▲" if chg > 0 else "▼"
            cat_changes.append(f"{cat} {direction}{abs(chg):,.0f} kb/d")
    if cat_changes:
        bullets.append("Notable w/w changes: " + ", ".join(cat_changes))

    # New outages (facilities offline today but NOT a week ago)
    facs_today = set(latest_off["facilityName"].unique())
    facs_wk_ago = set(wk_ago_off["facilityName"].unique()) if not wk_ago_off.empty else set()
    new_facs = facs_today - facs_wk_ago
    if new_facs:
        new_details = []
        for f in list(new_facs)[:5]:
            fdata = latest_off[latest_off["facilityName"] == f]
            cap = float(fdata["unitCapacity"].sum())
            cats = ", ".join(fdata["alternativeCategory"].unique()[:3])
            otype = fdata["outageType"].iloc[0] if not fdata.empty else ""
            new_details.append(f"{f} ({cats}, {cap:.0f} kb/d, {otype})")
        bullets.append("New offline this week: " + "; ".join(new_details))
        highlights.extend([{"facility": f, "capacity": float(latest_off[latest_off["facilityName"] == f]["unitCapacity"].sum()),
                            "type": str(latest_off[latest_off["facilityName"] == f]["outageType"].iloc[0]),
                            "categories": list(latest_off[latest_off["facilityName"] == f]["alternativeCategory"].unique()[:3])} for f in list(new_facs)[:5]])

    # Facilities returning (were offline last week, not today)
    returned_facs = facs_wk_ago - facs_today
    if returned_facs:
        ret_details = []
        for f in list(returned_facs)[:5]:
            fdata = wk_ago_off[wk_ago_off["facilityName"] == f]
            cap = float(fdata["unitCapacity"].sum())
            ret_details.append(f"{f} ({cap:.0f} kb/d)")
        bullets.append("Back online this week: " + "; ".join(ret_details))

    # Largest current outages
    top3 = latest_off.groupby("facilityName")["unitCapacity"].sum().sort_values(ascending=False).head(3)
    top3_str = [f"{name} ({val:,.0f} kb/d)" for name, val in top3.items()]
    if top3_str:
        bullets.append("Largest current outages: " + ", ".join(top3_str))

    # Unplanned outages specifically
    unplanned = latest_off[latest_off["outageType"].str.contains("Unplanned|Force", case=False, na=False)]
    if not unplanned.empty:
        unpl_kbd = float(unplanned["unitCapacity"].sum())
        unpl_count = len(unplanned["facilityName"].unique())
        bullets.append(f"Unplanned/forced outages: {unpl_kbd:,.0f} kb/d across {unpl_count} facilities")

    # PADD breakdown
    padd_summary = latest_off.groupby("region")["unitCapacity"].sum().sort_values(ascending=False)
    padd_str = [f"{p}: {v:,.0f}" for p, v in padd_summary.items()]
    if padd_str:
        bullets.append("By PADD (kb/d): " + " | ".join(padd_str))

    # EU/UK briefing (if data exists)
    eu_bullets = []
    eu_df = df[df["region"].isin(["Europe", "United Kingdom"])]
    if not eu_df.empty:
        eu_offline = eu_df[eu_df["unitOnline"] == False]
        eu_latest = eu_df["measurementDate"].max()
        eu_latest_off = eu_offline[eu_offline["measurementDate"] == eu_latest]
        if not eu_latest_off.empty:
            eu_total = float(eu_latest_off["unitCapacity"].sum())
            eu_units = len(eu_latest_off)
            eu_bullets.append(f"Europe/UK offline: {eu_total:,.0f} kb/d across {eu_units} units (as of {eu_latest.strftime('%b %d')})")
            # Top EU outages
            eu_top = eu_latest_off.groupby("facilityName")["unitCapacity"].sum().sort_values(ascending=False).head(3)
            eu_top_str = [f"{n} ({v:,.0f})" for n, v in eu_top.items()]
            if eu_top_str:
                eu_bullets.append("Top EU/UK outages: " + ", ".join(eu_top_str))

    return {
        "date": latest.strftime("%Y-%m-%d"),
        "bullets": bullets,
        "eu_bullets": eu_bullets,
        "highlights": highlights,
        "total_offline_kbd": round(total_offline_kbd, 0),
        "wow_change_kbd": round(wow_chg, 0),
    }


@app.get("/api/genscape/cushing_analytics")
async def genscape_cushing_analytics():
    """Cushing pipeline flow analytics: net flows, implied stock change, seasonal overlay, utilization."""
    api_key = os.environ.get("GSPE_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="Genscape API key not configured")

    import time as _time
    import http.client
    import urllib.parse
    import json

    # Pull daily pipeline data (last 90 days for charts)
    all_data = []
    end_date = pd.Timestamp.now().strftime("%Y-%m-%d")
    start_90 = (pd.Timestamp.now() - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    for offset in range(0, 50000, 5000):
        params = urllib.parse.urlencode({"limit": 5000, "offset": offset, "format": "json"})
        conn = http.client.HTTPSConnection("api.genscape.com")
        conn.request("GET", f"/transportation/oil/v1/pipeline-flows/daily?startDate={start_90}&endDate={end_date}&{params}",
                      "{body}", {"Gen-Api-Key": api_key})
        resp = conn.getresponse()
        if resp.status != 200:
            raise HTTPException(status_code=resp.status, detail="Genscape pipeline API error")
        batch = json.loads(resp.read()).get("data", [])
        all_data.extend(batch)
        conn.close()
        if len(batch) < 5000:
            break
        _time.sleep(2.1)

    if not all_data:
        raise HTTPException(status_code=404, detail="No pipeline data")

    df = pd.DataFrame(all_data)
    df["reportDate"] = pd.to_datetime(df["reportDate"])
    df["flowBpd"] = pd.to_numeric(df["flowBpd"], errors="coerce").fillna(0)
    df["pipelineCapacity"] = pd.to_numeric(df["pipelineCapacity"], errors="coerce").fillna(0)

    # Cushing daily aggregates
    cushing_in = df[df["direction"].str.contains("Cushing Incoming", na=False)].groupby("reportDate")["flowBpd"].sum()
    cushing_out = df[df["direction"] == "Cushing Outgoing"].groupby("reportDate")["flowBpd"].sum()
    all_dates = sorted(set(cushing_in.index) | set(cushing_out.index))

    daily_net = []
    cum_net = 0
    daily_flows = {"dates": [], "incoming": [], "outgoing": [], "net": [], "cumulative": []}
    for d in all_dates:
        inc = float(cushing_in.get(d, 0))
        out = float(cushing_out.get(d, 0))
        net = inc - out
        cum_net += net
        daily_flows["dates"].append(d.strftime("%Y-%m-%d"))
        daily_flows["incoming"].append(round(inc, 0))
        daily_flows["outgoing"].append(round(out, 0))
        daily_flows["net"].append(round(net, 0))
        daily_flows["cumulative"].append(round(cum_net, 0))

    # Patoka daily aggregates
    patoka_in = df[df["direction"] == "Patoka Incoming"].groupby("reportDate")["flowBpd"].sum()
    patoka_out = df[df["direction"] == "Patoka Outgoing"].groupby("reportDate")["flowBpd"].sum()
    patoka_flows = {"dates": [], "incoming": [], "outgoing": [], "net": []}
    for d in all_dates:
        if d in patoka_in.index or d in patoka_out.index:
            inc = float(patoka_in.get(d, 0))
            out = float(patoka_out.get(d, 0))
            patoka_flows["dates"].append(d.strftime("%Y-%m-%d"))
            patoka_flows["incoming"].append(round(inc, 0))
            patoka_flows["outgoing"].append(round(out, 0))
            patoka_flows["net"].append(round(inc - out, 0))

    # Pipeline utilization (latest day)
    latest_date = df["reportDate"].max()
    latest_pipes = df[df["reportDate"] == latest_date].copy()
    latest_pipes["utilization"] = (latest_pipes["flowBpd"] / latest_pipes["pipelineCapacity"] * 100).where(latest_pipes["pipelineCapacity"] > 0, 0)
    pipe_util = latest_pipes.sort_values("flowBpd", ascending=False)[
        ["pipelineName", "direction", "flowBpd", "pipelineCapacity", "utilization", "startPumpStation", "finishPumpStation"]
    ].to_dict("records")
    for p in pipe_util:
        p["flowBpd"] = round(float(p["flowBpd"]), 0)
        p["pipelineCapacity"] = round(float(p["pipelineCapacity"]), 0)
        p["utilization"] = round(float(p["utilization"]), 1)

    # Weekly implied stock change (group daily net into 7-day windows)
    weekly_stock = []
    if all_dates:
        wk_start = all_dates[0]
        wk_vals = []
        for d in all_dates:
            inc = float(cushing_in.get(d, 0))
            out = float(cushing_out.get(d, 0))
            wk_vals.append(inc - out)
            if len(wk_vals) == 7 or d == all_dates[-1]:
                avg_net = sum(wk_vals) / len(wk_vals)
                implied_change_mmbbl = avg_net * len(wk_vals) / 1_000_000
                weekly_stock.append({
                    "week_start": wk_start.strftime("%Y-%m-%d"),
                    "week_end": d.strftime("%Y-%m-%d"),
                    "avg_net_bpd": round(avg_net, 0),
                    "implied_change_mmbbl": round(implied_change_mmbbl, 3),
                    "days": len(wk_vals),
                })
                wk_start = d + pd.Timedelta(days=1)
                wk_vals = []

    # Latest summary stats
    latest_in = float(cushing_in.get(latest_date, 0))
    latest_out = float(cushing_out.get(latest_date, 0))

    return {
        "latest_date": latest_date.strftime("%Y-%m-%d"),
        "cushing_summary": {
            "incoming_bpd": round(latest_in, 0),
            "outgoing_bpd": round(latest_out, 0),
            "net_bpd": round(latest_in - latest_out, 0),
            "patoka_incoming": round(float(patoka_in.get(latest_date, 0)), 0),
            "patoka_outgoing": round(float(patoka_out.get(latest_date, 0)), 0),
        },
        "daily_flows": daily_flows,
        "patoka_flows": patoka_flows,
        "pipeline_utilization": pipe_util,
        "weekly_implied_stock": weekly_stock,
    }


# ---------------------------------------------------------------------------
# IIR (Industrial Info Resources) — Refinery Turnarounds & Offline Events
# ---------------------------------------------------------------------------
_IIR_BASE = "https://api.industrialinfo.com/idb/v2.4"
_IIR_TOKEN = None
_IIR_TOKEN_EXPIRY = None


def _iir_get_token() -> str:
    """Get or refresh IIR API JWT token."""
    import http.client
    import json as _json
    from datetime import datetime as _dt, timedelta, timezone

    global _IIR_TOKEN, _IIR_TOKEN_EXPIRY

    now = _dt.now(timezone.utc)
    if _IIR_TOKEN and _IIR_TOKEN_EXPIRY and now < _IIR_TOKEN_EXPIRY:
        return _IIR_TOKEN

    username = os.environ.get("IIR_USERNAME", "svcprd2025")
    password = os.environ.get("IIR_PASSWORD", "Energy25%21%21")

    conn = http.client.HTTPSConnection("api.industrialinfo.com")
    url = f"/idb/v2.4/token?username={username}&password={password}&tokenLifeTime=7"
    conn.request("POST", url)
    resp = conn.getresponse()
    headers = dict(resp.getheaders())
    body = resp.read()
    conn.close()

    token = None
    for k, v in headers.items():
        if k.lower() == "authorization":
            token = v.replace("Bearer ", "").replace("AUTHORIZATION: Bearer ", "").strip()
            break

    if not token:
        upstream = ""
        try:
            err = _json.loads(body)
            upstream = f" (IIR error #{err.get('code')}: {err.get('message', '')})"
        except Exception:
            pass
        raise HTTPException(
            status_code=502,
            detail=f"Failed to obtain IIR API token{upstream}. "
                   "This comes from IIR's server — if the credentials are correct, the account "
                   "may be locked/expired; contact IIR member services.")

    _IIR_TOKEN = token
    _IIR_TOKEN_EXPIRY = now + timedelta(days=6)
    return token


def _iir_fetch(endpoint: str, params: dict) -> dict:
    """Make a POST request to IIR API with query parameters."""
    import http.client
    import json as _json
    from urllib.parse import urlencode

    token = _iir_get_token()
    conn = http.client.HTTPSConnection("api.industrialinfo.com")
    qs = urlencode(params, doseq=True)
    url = f"/idb/v2.4/{endpoint}?{qs}"
    conn.request("POST", url, headers={"Authorization": f"Bearer {token}"})
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()

    if resp.status != 200:
        return {"error": f"IIR API returned {resp.status}", "detail": raw.decode()[:500]}

    import json as _json
    return _json.loads(raw)


def _iir_fetch_all_pages(endpoint: str, params: dict, max_pages: int = 20) -> list:
    """Fetch all pages from IIR API."""
    all_items = []
    key_map = {
        "offlineevents/summary": "offlineEvents",
        "offlineevents/detail": "offlineEvents",
        "plants/summary": "plants",
        "units/summary": "units",
        "projects/summary": "projects",
    }
    item_key = key_map.get(endpoint, "offlineEvents")

    for page in range(1, max_pages + 1):
        params["pageNumber"] = page
        params["pageSize"] = 100
        data = _iir_fetch(endpoint, params)
        items = data.get(item_key, [])
        all_items.extend(items)
        if len(items) < 100 or len(all_items) >= data.get("totalCount", 0):
            break

    return all_items


def _iir_dedup_events(events: list) -> list:
    """Deduplicate IIR events by plantName + unitTypeDesc + eventStartDate + eventEndDate.
    Keeps first occurrence (highest capacity if tied)."""
    seen = {}
    for e in events:
        key = (
            e.get("plantName", ""),
            e.get("unitTypeDesc", ""),
            (e.get("eventStartDate") or "")[:10],
            (e.get("eventEndDate") or "")[:10],
        )
        if key not in seen:
            seen[key] = e
        else:
            # Keep the one with higher capacity
            existing_cap = seen[key].get("offlineCapacity", {}).get("capacityOffline", 0) or 0
            new_cap = e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0
            if new_cap > existing_cap:
                seen[key] = e
    return list(seen.values())


@app.get("/api/iir/turnarounds")
async def iir_turnarounds(
    country: str = Query("U.S.A."),
    status: str = Query("Ongoing"),
    start_date_min: str = Query(None),
    event_kind: str = Query("T"),
    page_size: int = Query(100),
    page_number: int = Query(1),
):
    """Fetch refinery turnaround events from IIR."""
    params = {
        "eventKind": event_kind,
        "eventStatusDesc": status,
        "pageSize": page_size,
        "pageNumber": page_number,
    }
    if country:
        params["physicalAddressCountryName"] = country
    if start_date_min:
        params["eventStartDateMin"] = start_date_min

    data = _iir_fetch("offlineevents/summary", params)
    if "error" in data:
        raise HTTPException(status_code=502, detail=data["error"])
    return data


@app.get("/api/iir/turnarounds_all")
async def iir_turnarounds_all(
    country: str = Query("U.S.A."),
    status: str = Query("Ongoing"),
    start_date_min: str = Query(None),
    event_kind: str = Query("T"),
):
    """Fetch ALL refinery turnaround events (paginated internally)."""
    params = {
        "eventKind": event_kind,
        "eventStatusDesc": status,
    }
    if country:
        params["physicalAddressCountryName"] = country
    if start_date_min:
        params["eventStartDateMin"] = start_date_min

    events = _iir_fetch_all_pages("offlineevents/summary", params)

    # Aggregate statistics
    from collections import defaultdict
    by_plant = defaultdict(lambda: {"units": [], "total_offline": 0, "state": "", "region": ""})
    by_unit_type = defaultdict(lambda: {"count": 0, "total_offline": 0})
    by_state = defaultdict(lambda: {"count": 0, "total_offline": 0})
    total_offline = 0

    for e in events:
        plant = e.get("plantName", "Unknown")
        cap = e.get("offlineCapacity", {})
        offline = cap.get("capacityOffline", 0)
        unit_type = e.get("unitTypeDesc", "Unknown")
        state = e.get("plantPhysicalAddress", {}).get("stateName", "")
        region = e.get("tradingRegionName", "")

        by_plant[plant]["units"].append({
            "unitName": e.get("unitName", ""),
            "unitType": unit_type,
            "capacityOffline": offline,
            "unitCapacity": cap.get("unitCapacity", 0),
            "startDate": (e.get("associatedEntityStartDate") or "")[:10],
            "endDate": (e.get("associatedEntityEndDate") or "")[:10],
            "eventType": e.get("eventType", ""),
            "confirmation": e.get("eventConfirmationStatus", ""),
            "duration": e.get("eventDuration", 0),
            "eventId": e.get("eventId"),
            "comments": e.get("eventComments", ""),
        })
        by_plant[plant]["total_offline"] += offline
        by_plant[plant]["state"] = state
        by_plant[plant]["region"] = region

        by_unit_type[unit_type]["count"] += 1
        by_unit_type[unit_type]["total_offline"] += offline

        by_state[state]["count"] += 1
        by_state[state]["total_offline"] += offline

        total_offline += offline

    # Sort plants by offline capacity
    plants_sorted = sorted(by_plant.items(), key=lambda x: -x[1]["total_offline"])
    plant_list = []
    for name, info in plants_sorted:
        plant_list.append({
            "plantName": name,
            "state": info["state"],
            "region": info["region"],
            "totalOffline": round(info["total_offline"], 0),
            "unitCount": len(info["units"]),
            "units": sorted(info["units"], key=lambda u: -u["capacityOffline"]),
        })

    unit_types_sorted = sorted(by_unit_type.items(), key=lambda x: -x[1]["total_offline"])
    states_sorted = sorted(by_state.items(), key=lambda x: -x[1]["total_offline"])

    return {
        "status": status,
        "country": country,
        "totalEvents": len(events),
        "totalOfflineCapacity": round(total_offline, 0),
        "plants": plant_list,
        "byUnitType": [{"type": k, "count": v["count"], "offline": round(v["total_offline"], 0)} for k, v in unit_types_sorted],
        "byState": [{"state": k, "count": v["count"], "offline": round(v["total_offline"], 0)} for k, v in states_sorted],
        "events": events,
    }


@app.get("/api/iir/turnaround_calendar")
async def iir_turnaround_calendar(
    country: str = Query("U.S.A."),
    months_ahead: int = Query(12),
):
    """Get turnaround calendar — monthly aggregate of planned offline capacity."""
    from datetime import datetime as _dt, timedelta
    from collections import defaultdict

    # Get ongoing + future events
    all_events = []
    for status in ["Ongoing", "Future"]:
        params = {
            "eventKind": "T",
            "eventStatusDesc": status,
        }
        if country:
            params["physicalAddressCountryName"] = country
        events = _iir_fetch_all_pages("offlineevents/summary", params, max_pages=30)
        all_events.extend(events)

    # Build monthly offline capacity timeline
    now = _dt.now()
    monthly = defaultdict(lambda: {"offline_bpd": 0, "events": 0, "plants": set()})

    for e in all_events:
        start_str = (e.get("associatedEntityStartDate") or "")[:10]
        end_str = (e.get("associatedEntityEndDate") or "")[:10]
        if not start_str or not end_str:
            continue

        try:
            start = _dt.strptime(start_str, "%Y-%m-%d")
            end = _dt.strptime(end_str, "%Y-%m-%d")
        except ValueError:
            continue

        cap = e.get("offlineCapacity", {}).get("capacityOffline", 0)
        plant = e.get("plantName", "")

        # For each month this event spans
        cursor = _dt(start.year, start.month, 1)
        end_month = _dt(end.year, end.month, 1)
        while cursor <= end_month:
            month_key = cursor.strftime("%Y-%m")
            # Calculate fraction of month offline
            month_start = cursor
            if cursor.month == 12:
                month_end = _dt(cursor.year + 1, 1, 1)
            else:
                month_end = _dt(cursor.year, cursor.month + 1, 1)
            days_in_month = (month_end - month_start).days

            overlap_start = max(start, month_start)
            overlap_end = min(end, month_end - timedelta(days=1))
            overlap_days = max(0, (overlap_end - overlap_start).days + 1)

            if overlap_days > 0:
                monthly[month_key]["offline_bpd"] += cap * overlap_days / days_in_month
                monthly[month_key]["events"] += 1
                monthly[month_key]["plants"].add(plant)

            if cursor.month == 12:
                cursor = _dt(cursor.year + 1, 1, 1)
            else:
                cursor = _dt(cursor.year, cursor.month + 1, 1)

    # Sort and format
    sorted_months = sorted(monthly.items())
    calendar = []
    for month, data in sorted_months:
        calendar.append({
            "month": month,
            "avgOfflineBpd": round(data["offline_bpd"], 0),
            "eventCount": data["events"],
            "plantCount": len(data["plants"]),
        })

    return {
        "country": country,
        "calendar": calendar,
        "totalEvents": len(all_events),
    }


@app.get("/api/iir/dashboard")
async def iir_dashboard(country: str = Query("U.S.A.")):
    """Comprehensive IIR dashboard — ongoing, upcoming, recent past turnarounds."""
    from collections import defaultdict
    from datetime import datetime as _dt, timedelta

    results = {}

    # 1. Ongoing turnarounds
    ongoing_params = {"eventKind": "T", "eventStatusDesc": "Ongoing"}
    if country:
        ongoing_params["physicalAddressCountryName"] = country
    ongoing_raw = _iir_fetch_all_pages("offlineevents/summary", ongoing_params)
    ongoing = _iir_dedup_events(ongoing_raw)
    results["ongoing"] = {
        "count": len(ongoing),
        "events": ongoing,
    }

    # 2. Future turnarounds (next 12 months)
    future_params = {"eventKind": "T", "eventStatusDesc": "Future"}
    if country:
        future_params["physicalAddressCountryName"] = country
    future_raw = _iir_fetch_all_pages("offlineevents/summary", future_params, max_pages=30)
    future_events = _iir_dedup_events(future_raw)
    results["future"] = {
        "count": len(future_events),
        "events": future_events,
    }

    # 3. Recent past (last 6 months)
    six_months_ago = (_dt.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    past_params = {"eventKind": "T", "eventStatusDesc": "Past", "eventStartDateMin": six_months_ago}
    if country:
        past_params["physicalAddressCountryName"] = country
    past_raw = _iir_fetch_all_pages("offlineevents/summary", past_params, max_pages=30)
    past_events = _iir_dedup_events(past_raw)
    results["past"] = {
        "count": len(past_events),
        "events": past_events,
    }

    # 4. Aggregate stats
    all_events = ongoing + future_events + past_events
    by_unit_type = defaultdict(lambda: {"ongoing": 0, "future": 0, "past": 0})
    by_state = defaultdict(lambda: {"ongoing": 0, "future": 0, "past": 0})

    for e in ongoing:
        ut = e.get("unitTypeDesc", "Other")
        cap = e.get("offlineCapacity", {}).get("capacityOffline", 0)
        st = e.get("plantPhysicalAddress", {}).get("stateName", "")
        by_unit_type[ut]["ongoing"] += cap
        by_state[st]["ongoing"] += cap

    for e in future_events:
        ut = e.get("unitTypeDesc", "Other")
        cap = e.get("offlineCapacity", {}).get("capacityOffline", 0)
        st = e.get("plantPhysicalAddress", {}).get("stateName", "")
        by_unit_type[ut]["future"] += cap
        by_state[st]["future"] += cap

    results["byUnitType"] = {k: v for k, v in sorted(by_unit_type.items(), key=lambda x: -(x[1]["ongoing"] + x[1]["future"]))}
    results["byState"] = {k: v for k, v in sorted(by_state.items(), key=lambda x: -(x[1]["ongoing"] + x[1]["future"]))}

    # Sync to Azure SQL if configured
    if _DB_AVAILABLE and is_db_enabled():
        try:
            _db_refresh_iir(ongoing, "Ongoing", country)
            _db_refresh_iir(future_events, "Future", country)
            _db_refresh_iir(past_events, "Past", country)
        except Exception:
            pass  # Non-blocking — don't fail the API response

    return results


@app.get("/api/iir/briefing")
async def iir_briefing(country: str = Query("U.S.A.")):
    """Auto-generated trader briefing for IIR turnaround data."""
    from collections import defaultdict
    from datetime import datetime as _dt, timedelta

    bullets = []
    highlights = []

    # Ongoing turnarounds (deduped)
    ongoing_params = {"eventKind": "T", "eventStatusDesc": "Ongoing"}
    if country:
        ongoing_params["physicalAddressCountryName"] = country
    ongoing = _iir_dedup_events(_iir_fetch_all_pages("offlineevents/summary", ongoing_params))

    total_ongoing = len(ongoing)
    total_offline_cap = sum(e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0 for e in ongoing)

    bullets.append(f"Currently {total_ongoing} ongoing turnarounds in {country} with {total_offline_cap:,.0f} b/d total offline capacity")

    # By unit type
    by_type = defaultdict(lambda: {"count": 0, "cap": 0})
    for e in ongoing:
        ut = e.get("unitTypeDesc", "Other")
        cap = e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0
        by_type[ut]["count"] += 1
        by_type[ut]["cap"] += cap
    sorted_types = sorted(by_type.items(), key=lambda x: -x[1]["cap"])
    type_str = [f"{t}: {v['cap']:,.0f} b/d ({v['count']} units)" for t, v in sorted_types[:5]]
    if type_str:
        bullets.append("By unit type — " + " | ".join(type_str))

    # Unplanned/forced outages
    unplanned = [e for e in ongoing if "unplanned" in str(e.get("eventTypeDesc", "")).lower() or "force" in str(e.get("eventTypeDesc", "")).lower()]
    if unplanned:
        unpl_cap = sum(e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0 for e in unplanned)
        bullets.append(f"Unplanned/forced outages: {len(unplanned)} events, {unpl_cap:,.0f} b/d offline")

    # Top ongoing by capacity
    ongoing_sorted = sorted(ongoing, key=lambda e: -(e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0))
    top5 = ongoing_sorted[:5]
    top_details = []
    for e in top5:
        plant = e.get("plantName", "Unknown")
        unit = e.get("unitTypeDesc", "")
        cap = e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0
        start = e.get("eventStartDate", "")[:10]
        end = e.get("eventEndDate", "")[:10]
        confirm = e.get("confirmationLevel", "")
        top_details.append(f"{plant} — {unit} ({cap:,.0f} b/d, {start} to {end}, {confirm})")
        highlights.append({"plant": plant, "unit": unit, "capacity": cap, "start": start, "end": end, "confirmation": confirm})
    if top_details:
        bullets.append("Largest ongoing outages:")
        bullets.extend([f"  • {d}" for d in top_details])

    # Recently started (in last 7 days) — already deduped from ongoing
    now = _dt.now()
    recent_start = [e for e in ongoing if e.get("eventStartDate") and (_dt.now() - _dt.fromisoformat(e["eventStartDate"][:10])).days <= 7]
    if recent_start:
        rec_cap = sum(e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0 for e in recent_start)
        bullets.append(f"Started in last 7 days: {len(recent_start)} events adding {rec_cap:,.0f} b/d offline")
        for e in recent_start[:5]:
            plant = e.get("plantName", "Unknown")
            unit = e.get("unitTypeDesc", "")
            cap = e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0
            bullets.append(f"  • NEW: {plant} — {unit} ({cap:,.0f} b/d, started {e.get('eventStartDate', '')[:10]})")

    # Ending soon (within next 7 days) — already deduped from ongoing
    ending_soon = [e for e in ongoing if e.get("eventEndDate") and 0 <= (_dt.fromisoformat(e["eventEndDate"][:10]) - now).days <= 7]
    if ending_soon:
        end_cap = sum(e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0 for e in ending_soon)
        bullets.append(f"Expected back online within 7 days: {len(ending_soon)} events, {end_cap:,.0f} b/d returning")
        for e in ending_soon[:5]:
            plant = e.get("plantName", "Unknown")
            unit = e.get("unitTypeDesc", "")
            cap = e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0
            bullets.append(f"  • RETURNING: {plant} — {unit} ({cap:,.0f} b/d, ends {e.get('eventEndDate', '')[:10]})")

    # Future upcoming (next 30 days)
    future_params = {"eventKind": "T", "eventStatusDesc": "Future", "eventStartDateMin": now.strftime("%Y-%m-%d"), "eventStartDateMax": (now + timedelta(days=30)).strftime("%Y-%m-%d")}
    if country:
        future_params["physicalAddressCountryName"] = country
    future_30 = _iir_dedup_events(_iir_fetch_all_pages("offlineevents/summary", future_params, max_pages=5))
    if future_30:
        fut_cap = sum(e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0 for e in future_30)
        bullets.append(f"Planned for next 30 days: {len(future_30)} turnarounds, {fut_cap:,.0f} b/d expected offline")

    return {
        "country": country,
        "bullets": bullets,
        "highlights": highlights,
        "total_ongoing": total_ongoing,
        "total_offline_capacity": total_offline_cap,
    }


@app.get("/api/iir/seasonal")
async def iir_seasonal(country: str = Query("U.S.A.")):
    """Seasonal offline capacity overlay — historical turnarounds by year for comparison."""
    from collections import defaultdict
    from datetime import datetime as _dt, timedelta, date as _date

    # Default to U.S.A. if empty (All Countries too slow for IIR API)
    if not country:
        country = "U.S.A."

    # Get past 3 years + current year of turnarounds
    all_events = []
    for status in ["Past", "Ongoing"]:
        params = {"eventKind": "T", "eventStatusDesc": status,
                  "physicalAddressCountryName": country}
        if status == "Past":
            params["eventStartDateMin"] = (_dt.now() - timedelta(days=3*365)).strftime("%Y-%m-%d")
        try:
            events = _iir_dedup_events(_iir_fetch_all_pages("offlineevents/summary", params, max_pages=30))
            all_events.extend(events)
        except Exception:
            pass  # skip if API times out for one status

    if not all_events:
        return {"seasonal": {}, "country": country}

    # Build weekly offline capacity by year
    # For each event, it contributes its capacity to every week it spans
    yearly_weekly = defaultdict(lambda: defaultdict(float))  # year -> week_num -> total_cap

    for e in all_events:
        start_str = (e.get("eventStartDate") or "")[:10]
        end_str = (e.get("eventEndDate") or "")[:10]
        cap = e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0
        if not start_str or not end_str or cap <= 0:
            continue
        try:
            start_d = _date.fromisoformat(start_str)
            end_d = _date.fromisoformat(end_str)
        except (ValueError, TypeError):
            continue
        # Cap end date to avoid runaway loops
        max_end = start_d + timedelta(days=365)
        if end_d > max_end:
            end_d = max_end
        # Walk through each week the event spans
        d = start_d
        while d <= end_d:
            yr = d.year
            wk = d.isocalendar()[1]
            yearly_weekly[yr][wk] += cap
            d += timedelta(days=7)

    # Format output
    seasonal = {}
    for yr in sorted(yearly_weekly.keys()):
        weeks = sorted(yearly_weekly[yr].keys())
        seasonal[yr] = {
            "weeks": weeks,
            "values": [round(yearly_weekly[yr][w], 0) for w in weeks],
        }

    return {"seasonal": seasonal, "country": country}


@app.get("/api/iir/refineries")
async def iir_refineries(country: str = Query("U.S.A.")):
    """List all refineries for a country with status summary (ongoing/future/past event counts)."""
    from collections import defaultdict
    from datetime import datetime as _dt, timedelta

    plant_info: dict = defaultdict(lambda: {
        "state": "", "region": "", "total_capacity": 0,
        "ongoing_offline": 0, "ongoing_events": 0,
        "future_events": 0, "past_events": 0,
        "unit_types": set(), "last_event_end": "",
    })

    # Fetch ongoing, future, past (last 2 years)
    two_years_ago = (_dt.now() - timedelta(days=730)).strftime("%Y-%m-%d")
    fetches = [
        ("Ongoing", {}),
        ("Future", {}),
        ("Past", {"eventStartDateMin": two_years_ago}),
    ]
    for status, extra in fetches:
        params = {"eventKind": "T", "eventStatusDesc": status}
        if country:
            params["physicalAddressCountryName"] = country
        params.update(extra)
        try:
            events = _iir_dedup_events(
                _iir_fetch_all_pages("offlineevents/summary", params, max_pages=30)
            )
        except Exception:
            events = []

        for e in events:
            pn = e.get("plantName", "Unknown")
            cap = e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0
            unit_cap = e.get("offlineCapacity", {}).get("unitCapacity", 0) or 0
            info = plant_info[pn]
            info["state"] = info["state"] or e.get("plantPhysicalAddress", {}).get("stateName", "")
            info["region"] = info["region"] or e.get("tradingRegionName", "")
            if unit_cap > info["total_capacity"]:
                info["total_capacity"] = unit_cap
            info["unit_types"].add(e.get("unitTypeDesc", ""))
            end_date = (e.get("associatedEntityEndDate") or "")[:10]
            if end_date > info["last_event_end"]:
                info["last_event_end"] = end_date

            if status == "Ongoing":
                info["ongoing_offline"] += cap
                info["ongoing_events"] += 1
            elif status == "Future":
                info["future_events"] += 1
            else:
                info["past_events"] += 1

    # Build sorted list
    refineries = []
    for pn, info in sorted(plant_info.items(), key=lambda x: x[0]):
        refineries.append({
            "plantName": pn,
            "state": info["state"],
            "region": info["region"],
            "ongoingOffline": round(info["ongoing_offline"], 0),
            "ongoingEvents": info["ongoing_events"],
            "futureEvents": info["future_events"],
            "pastEvents": info["past_events"],
            "totalEvents": info["ongoing_events"] + info["future_events"] + info["past_events"],
            "unitTypes": sorted(info["unit_types"] - {""}),
            "lastEventEnd": info["last_event_end"],
        })

    # Sort: ongoing first (by offline desc), then by total events
    refineries.sort(key=lambda r: (-r["ongoingOffline"], -r["totalEvents"]))

    return {
        "country": country,
        "totalRefineries": len(refineries),
        "refineries": refineries,
    }


@app.get("/api/iir/refinery_detail")
async def iir_refinery_detail(
    plant_name: str = Query(...),
    country: str = Query("U.S.A."),
):
    """Get full history of IIR events for a specific refinery, plus current status."""
    from collections import defaultdict
    from datetime import datetime as _dt, timedelta

    all_events = []

    # Fetch ongoing, future, and past (up to 5 years back) for this plant
    five_years_ago = (_dt.now() - timedelta(days=5 * 365)).strftime("%Y-%m-%d")
    fetches = [
        ("Ongoing", {}),
        ("Future", {}),
        ("Past", {"eventStartDateMin": five_years_ago}),
    ]
    for status, extra in fetches:
        params = {
            "eventKind": "T",
            "eventStatusDesc": status,
            "plantName": plant_name,
        }
        if country:
            params["physicalAddressCountryName"] = country
        params.update(extra)
        try:
            events = _iir_fetch_all_pages("offlineevents/summary", params, max_pages=30)
        except Exception:
            events = []

        for e in events:
            cap_obj = e.get("offlineCapacity", {})
            all_events.append({
                "eventId": e.get("eventId"),
                "plantName": e.get("plantName", ""),
                "unitName": e.get("unitName", ""),
                "unitTypeDesc": e.get("unitTypeDesc", ""),
                "capacityOffline": cap_obj.get("capacityOffline", 0) or 0,
                "unitCapacity": cap_obj.get("unitCapacity", 0) or 0,
                "startDate": (e.get("associatedEntityStartDate") or e.get("eventStartDate") or "")[:10],
                "endDate": (e.get("associatedEntityEndDate") or e.get("eventEndDate") or "")[:10],
                "eventType": e.get("eventType", ""),
                "eventStatus": status,
                "confirmation": e.get("eventConfirmationStatus", ""),
                "duration": e.get("eventDuration", 0),
                "comments": e.get("eventComments", ""),
                "state": e.get("plantPhysicalAddress", {}).get("stateName", ""),
                "region": e.get("tradingRegionName", ""),
            })

    # Deduplicate by unitName + startDate + endDate
    seen = {}
    deduped = []
    for ev in all_events:
        key = (ev["unitName"], ev["unitTypeDesc"], ev["startDate"], ev["endDate"])
        if key not in seen:
            seen[key] = ev
            deduped.append(ev)
        else:
            if ev["capacityOffline"] > seen[key]["capacityOffline"]:
                seen[key].update(ev)

    # Sort by start date descending (most recent first)
    deduped.sort(key=lambda e: e["startDate"], reverse=True)

    # Current status: ongoing events
    ongoing = [e for e in deduped if e["eventStatus"] == "Ongoing"]
    future = [e for e in deduped if e["eventStatus"] == "Future"]
    past = [e for e in deduped if e["eventStatus"] == "Past"]

    current_offline = sum(e["capacityOffline"] for e in ongoing)
    state = deduped[0]["state"] if deduped else ""
    region = deduped[0]["region"] if deduped else ""

    # Build monthly offline capacity timeline for chart
    monthly_offline: dict = defaultdict(float)
    monthly_events: dict = defaultdict(int)
    for ev in deduped:
        if not ev["startDate"] or not ev["endDate"]:
            continue
        try:
            start = _dt.strptime(ev["startDate"], "%Y-%m-%d")
            end = _dt.strptime(ev["endDate"], "%Y-%m-%d")
        except ValueError:
            continue
        cap = ev["capacityOffline"]
        if cap <= 0:
            continue
        # Walk months
        cursor = _dt(start.year, start.month, 1)
        end_month = _dt(end.year, end.month, 1)
        max_end = _dt(start.year + 2, start.month, 1)  # safety cap
        if end_month > max_end:
            end_month = max_end
        while cursor <= end_month:
            month_key = cursor.strftime("%Y-%m")
            if cursor.month == 12:
                month_end = _dt(cursor.year + 1, 1, 1)
            else:
                month_end = _dt(cursor.year, cursor.month + 1, 1)
            days_in_month = (month_end - _dt(cursor.year, cursor.month, 1)).days
            overlap_start = max(start, cursor)
            overlap_end = min(end, month_end - timedelta(days=1))
            overlap_days = max(0, (overlap_end - overlap_start).days + 1)
            if overlap_days > 0:
                monthly_offline[month_key] += cap * overlap_days / days_in_month
                monthly_events[month_key] += 1
            if cursor.month == 12:
                cursor = _dt(cursor.year + 1, 1, 1)
            else:
                cursor = _dt(cursor.year, cursor.month + 1, 1)

    sorted_months = sorted(monthly_offline.keys())
    timeline = [
        {"month": m, "offlineBpd": round(monthly_offline[m], 0), "events": monthly_events[m]}
        for m in sorted_months
    ]

    # Unit types summary
    unit_summary: dict = defaultdict(lambda: {"events": 0, "total_offline_days": 0, "max_capacity": 0})
    for ev in deduped:
        ut = ev["unitTypeDesc"] or "Unknown"
        unit_summary[ut]["events"] += 1
        unit_summary[ut]["total_offline_days"] += ev["duration"] or 0
        if ev["capacityOffline"] > unit_summary[ut]["max_capacity"]:
            unit_summary[ut]["max_capacity"] = ev["capacityOffline"]
    units_list = [
        {"unitType": k, "events": v["events"], "totalOfflineDays": v["total_offline_days"], "maxCapacity": v["max_capacity"]}
        for k, v in sorted(unit_summary.items(), key=lambda x: -x[1]["events"])
    ]

    return {
        "plantName": plant_name,
        "country": country,
        "state": state,
        "region": region,
        "currentStatus": "Offline" if ongoing else ("Upcoming" if future else "Online"),
        "currentOfflineBpd": round(current_offline, 0),
        "ongoingEvents": ongoing,
        "futureEvents": future,
        "pastEvents": past,
        "allEvents": deduped,
        "totalEvents": len(deduped),
        "timeline": timeline,
        "unitSummary": units_list,
    }


# --- LEM (Light Ends Market) ---
@app.get("/api/lem/data")
async def lem_data():
    """Return LEM gasoline/naphtha balance data (quarterly dataset)."""
    return await lem_quarterly()


@app.get("/api/lem/quarterly")
async def lem_quarterly():
    """Return quarterly light-ends balances (gasoline/naphtha) with analyst notes."""
    path = os.path.join(os.path.dirname(__file__), "lem_quarterly.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Quarterly LEM data not available")
    with open(path) as f:
        return _json.load(f)


# --- Local Balances (Energy Aspects global gasoline + US weekly) ────────────
_LOCALBAL_CACHE = None


def _load_local_balances():
    """Load the parsed Energy Aspects gasoline balance workbooks."""
    global _LOCALBAL_CACHE
    if _LOCALBAL_CACHE is None:
        path = os.path.join(os.path.dirname(__file__), "local_balances.json")
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Local balances data not available")
        with open(path) as f:
            _LOCALBAL_CACHE = _json.load(f)
    return _LOCALBAL_CACHE


def _lb_avg(vals):
    xs = [v for v in vals if v is not None]
    return sum(xs) / len(xs) if xs else None


@app.get("/api/localbal/regions")
async def localbal_regions():
    """List regions/countries available plus release metadata."""
    d = _load_local_balances()
    return {
        "as_of": d["as_of"],
        "release_date": d["release_date"],
        "source": d["source"],
        "regions": [{"code": c, "name": r["name"]} for c, r in d["regions"].items()],
        "countries": {c: sorted(v["countries"].keys()) for c, v in d["countries"].items()},
    }


@app.get("/api/localbal/region")
async def localbal_region(code: str = Query("WORLD"), country: str = Query(None)):
    """Monthly demand/supply/balance series for a region (or one country)."""
    d = _load_local_balances()
    reg = d["regions"].get(code)
    if reg is None:
        raise HTTPException(status_code=404, detail=f"Unknown region {code}")
    out = {"as_of": d["as_of"], "code": code, "name": reg["name"],
           "dates": reg["dates"], "demand": reg["demand"], "supply": reg["supply"],
           "balance": reg["balance"],
           "demand_fstart": reg.get("demand_fstart"), "supply_fstart": reg.get("supply_fstart")}
    if country:
        creg = d["countries"].get(code, {})
        c = creg.get("countries", {}).get(country)
        if c is None:
            raise HTTPException(status_code=404, detail=f"Unknown country {country}")
        cd, cs = c.get("demand"), c.get("supply")
        out["country"] = {
            "name": country, "dates": creg["dates"], "demand": cd, "supply": cs,
            "balance": [
                round(s - dm, 1) if (s is not None and dm is not None) else None
                for s, dm in zip(cs or [], cd or [])
            ] if (cs and cd) else None,
        }
    return out


@app.get("/api/localbal/summary")
async def localbal_summary():
    """Key takeaways per region + overall ideas, anchored to the as-of date."""
    d = _load_local_balances()
    as_of = d["as_of"]                       # 2026-07-13
    cur_m = as_of[:7] + "-01"                # 2026-07-01
    takeaways, tightening = [], []
    for code, reg in d["regions"].items():
        dates = reg["dates"]
        if cur_m not in dates:
            continue
        i = dates.index(cur_m)
        dem, sup, bal = reg["demand"], reg["supply"], reg["balance"]
        yoy = None
        if i >= 12 and dem[i] is not None and dem[i - 12]:
            yoy = round(dem[i] - dem[i - 12], 1)
        bal_now = _lb_avg(bal[max(0, i - 2):i + 1])
        bal_next = _lb_avg(bal[i + 1:i + 4])
        bal_yr_ago = _lb_avg(bal[max(0, i - 14):i - 11]) if i >= 14 else None
        delta = (round(bal_now - bal_yr_ago, 1)
                 if bal_now is not None and bal_yr_ago is not None else None)
        takeaways.append({
            "code": code, "name": reg["name"],
            "demand": dem[i], "supply": sup[i], "balance": bal[i],
            "demand_yoy": yoy,
            "balance_3m": round(bal_now, 1) if bal_now is not None else None,
            "balance_next3m": round(bal_next, 1) if bal_next is not None else None,
            "balance_vs_yr_ago": delta,
        })
        if delta is not None and code != "WORLD":
            tightening.append((delta, reg["name"]))
    tightening.sort()
    us = d["us_weekly"]["areas"].get("US", {})
    us_out = {}
    if us:
        dates = us["dates"]
        idx = [i for i, dt in enumerate(dates) if dt <= as_of]
        if idx:
            i = idx[-1]
            stocks = us.get("stocks", [])
            us_out = {
                "last_week": dates[i],
                "stocks_mb": round(stocks[i] / 1000, 1) if stocks[i] is not None else None,
                "stocks_yoy_mb": (round((stocks[i] - stocks[i - 52]) / 1000, 1)
                                  if i >= 52 and stocks[i] is not None and stocks[i - 52] is not None else None),
                "fcst_weeks": len(dates) - 1 - i,
                "fcst_stock_change_kbd": _lb_avg((us.get("stock_change") or [])[i + 1:]),
            }
    return {
        "as_of": as_of, "release_date": d["release_date"], "source": d["source"],
        "regions": takeaways,
        "tightening_most": [n for _, n in tightening[:3]],
        "loosening_most": [n for _, n in tightening[-3:]][::-1],
        "us": us_out,
    }


@app.get("/api/localbal/usweekly")
async def localbal_usweekly(area: str = Query("US")):
    """Weekly US/PADD gasoline balance table incl. EA forecast weeks."""
    d = _load_local_balances()
    a = d["us_weekly"]["areas"].get(area)
    if a is None:
        raise HTTPException(status_code=404, detail=f"Unknown area {area}")
    return {"as_of": d["as_of"], "release_date": d["release_date"],
            "source": d["source"], "area": area,
            "areas": list(d["us_weekly"]["areas"].keys()), "data": a}


# ===================================================================
# Azure SQL Database Integration
# ===================================================================
# Import DB module (graceful fallback if not installed)
try:
    from db.connection import is_db_enabled, test_connection as _db_test_connection
    from db.refresh import (
        refresh_genscape_us as _db_refresh_genscape_us,
        refresh_genscape_eu as _db_refresh_genscape_eu,
        refresh_iir_events as _db_refresh_iir,
        get_genscape_us_data as _db_get_genscape_us,
        get_genscape_eu_data as _db_get_genscape_eu,
        get_iir_events as _db_get_iir,
        get_refresh_log as _db_get_refresh_log,
    )
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False
    def is_db_enabled(): return False


@app.get("/api/db/status")
async def db_status():
    """Check Azure SQL Database connection status."""
    if not _DB_AVAILABLE:
        return {"status": "not_installed", "message": "DB modules not available (pyodbc/sqlalchemy not installed)"}
    return _db_test_connection()


@app.get("/api/db/refresh_log")
async def db_refresh_log(source: str = Query(None), limit: int = Query(20)):
    """View recent data refresh log entries."""
    if not _DB_AVAILABLE or not is_db_enabled():
        return {"error": "Database not configured"}
    df = _db_get_refresh_log(source, limit)
    if df is None or df.empty:
        return {"log": []}
    return {"log": df.to_dict(orient="records")}


@app.post("/api/db/sync_iir")
async def db_sync_iir(country: str = Query("U.S.A.")):
    """Sync current IIR dashboard data to Azure SQL."""
    if not _DB_AVAILABLE or not is_db_enabled():
        return {"error": "Database not configured"}

    from datetime import datetime as _dt, timedelta
    counts = {}

    for status_desc in ["Ongoing", "Future"]:
        params = {"eventKind": "T", "eventStatusDesc": status_desc}
        if country:
            params["physicalAddressCountryName"] = country
        raw = _iir_fetch_all_pages("offlineevents/summary", params, max_pages=30)
        deduped = _iir_dedup_events(raw)
        n = _db_refresh_iir(deduped, status_desc, country)
        counts[status_desc] = n

    six_months_ago = (_dt.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    past_params = {"eventKind": "T", "eventStatusDesc": "Past", "eventStartDateMin": six_months_ago}
    if country:
        past_params["physicalAddressCountryName"] = country
    past_raw = _iir_fetch_all_pages("offlineevents/summary", past_params, max_pages=30)
    past_deduped = _iir_dedup_events(past_raw)
    counts["Past"] = _db_refresh_iir(past_deduped, "Past", country)

    return {"status": "ok", "synced": counts, "country": country}


# --- Kpler → Azure SQL Sync ---

@app.post("/api/kpler/sync_sql")
async def kpler_sync_sql(tables: str = Query(None)):
    """
    Sync Kpler data → Azure SQL Database.
    
    Optional query param 'tables' = comma-separated list of table names.
    If omitted, syncs all tables.
    
    Example: /api/kpler/sync_sql?tables=Kpler_Flows,Kpler_Trades
    """
    # Check SQL credentials
    sql_server = os.environ.get("AZURE_SQL_SERVER", "")
    sql_user = os.environ.get("AZURE_SQL_USERNAME", "")
    sql_pass = os.environ.get("AZURE_SQL_PASSWORD", "")
    if not sql_server or not sql_user or not sql_pass:
        return {"error": "Azure SQL not configured. Set AZURE_SQL_SERVER, AZURE_SQL_DATABASE, AZURE_SQL_USERNAME, AZURE_SQL_PASSWORD env vars."}

    # Check Kpler credentials
    kpler_user = os.environ.get("KPLER_USERNAME", "")
    kpler_pass = os.environ.get("KPLER_PASSWORD", "")
    if not kpler_user or not kpler_pass:
        return {"error": "Kpler not configured. Set KPLER_USERNAME, KPLER_PASSWORD env vars."}

    try:
        from db.kpler_sync import sync_all
        table_list = [t.strip() for t in tables.split(",")] if tables else None
        result = sync_all(tables=table_list)
        return result
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()[:2000]}


@app.get("/api/kpler/sync_status")
async def kpler_sync_status():
    """Check last sync status for each Kpler table."""
    sql_server = os.environ.get("AZURE_SQL_SERVER", "")
    sql_user = os.environ.get("AZURE_SQL_USERNAME", "")
    if not sql_server or not sql_user:
        return {"configured": False, "message": "Azure SQL credentials not set"}

    try:
        from db.kpler_sync import _get_sql_conn
        conn = _get_sql_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name, sync_start, sync_end, rows_inserted, status, error_message
            FROM dbo.Kpler_SyncLog
            WHERE id IN (SELECT MAX(id) FROM dbo.Kpler_SyncLog GROUP BY table_name)
            ORDER BY table_name
        """)
        rows = cursor.fetchall()
        conn.close()
        return {
            "configured": True,
            "server": sql_server,
            "last_syncs": [
                {
                    "table": r.table_name,
                    "sync_start": str(r.sync_start) if r.sync_start else None,
                    "sync_end": str(r.sync_end) if r.sync_end else None,
                    "rows": r.rows_inserted,
                    "status": r.status,
                    "error": r.error_message[:200] if r.error_message else None,
                }
                for r in rows
            ],
        }
    except Exception as e:
        return {"configured": True, "error": str(e)[:300]}


# ============================================================
# Signal Ocean tanker data (Azure SQL, read-only)
# Env: SIGNAL_SQL_SERVER (host,port), SIGNAL_SQL_USERNAME, SIGNAL_SQL_PASSWORD,
#      SIGNAL_SQL_DATABASE (optional), SIGNAL_PASSAGES_SQL (optional override)
# ============================================================
import re as _re
import time as _time
import threading as _threading

SIGNAL_SCHEMA_TTL = 3600
SIGNAL_DATA_TTL = 900
_signal_cache: dict = {"schema": None, "schema_ts": 0, "data": {}}
_signal_lock = _threading.Lock()

_SIGNAL_STRAIT_HINTS = ("strait", "passage", "chokepoint", "choke_point", "canal", "transit", "waterway", "geo_area", "area_name")
_SIGNAL_DATE_HINTS = ("passage_date", "transit_date", "date", "timestamp", "datetime", "day")
_SIGNAL_CLASS_HINTS = ("vessel_class", "vesselclass", "vessel_type", "class", "size", "segment")
_SIGNAL_VESSEL_HINTS = ("imo", "vessel_id", "vesselid", "vessel_name", "vesselname", "mmsi")
_SIGNAL_DIR_HINTS = ("direction", "heading", "bound", "north", "south", "east", "west")
_SIGNAL_CLASS_ALIASES = {
    "vlcc": "VLCC", "suezmax": "Suezmax", "aframax": "Aframax", "afra": "Aframax",
}


def _signal_configured() -> bool:
    return bool(os.environ.get("SIGNAL_SQL_SERVER") and os.environ.get("SIGNAL_SQL_USERNAME") and os.environ.get("SIGNAL_SQL_PASSWORD"))


def _signal_conn():
    import pyodbc
    server = os.environ.get("SIGNAL_SQL_SERVER", "")
    database = os.environ.get("SIGNAL_SQL_DATABASE", "")
    driver = os.environ.get("SIGNAL_SQL_DRIVER", "ODBC Driver 18 for SQL Server")
    cs = (
        f"DRIVER={{{driver}}};SERVER={server};"
        + (f"DATABASE={database};" if database else "")
        + f"UID={os.environ.get('SIGNAL_SQL_USERNAME', '')};"
        + f"PWD={{{os.environ.get('SIGNAL_SQL_PASSWORD', '')}}};"
        + "Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=25;ApplicationIntent=ReadOnly;"
    )
    return pyodbc.connect(cs, autocommit=True, timeout=60)


def _signal_rows(sql: str, params: tuple = ()) -> list[dict]:
    conn = _signal_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        out = []
        for r in cur.fetchall():
            row = {}
            for c, v in zip(cols, r):
                if hasattr(v, "isoformat"):
                    v = v.isoformat()
                elif isinstance(v, (bytes, bytearray)):
                    v = v.hex()
                elif v is not None and not isinstance(v, (int, float, str, bool)):
                    v = float(v) if hasattr(v, "__float__") else str(v)
                row[c] = v
            out.append(row)
        return out
    finally:
        conn.close()


def _signal_schema(force: bool = False) -> dict:
    now = _time.time()
    with _signal_lock:
        if not force and _signal_cache["schema"] and now - _signal_cache["schema_ts"] < SIGNAL_SCHEMA_TTL:
            return _signal_cache["schema"]
    rows = _signal_rows(
        "SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.ORDINAL_POSITION, t.TABLE_TYPE "
        "FROM INFORMATION_SCHEMA.COLUMNS c JOIN INFORMATION_SCHEMA.TABLES t "
        "ON c.TABLE_SCHEMA = t.TABLE_SCHEMA AND c.TABLE_NAME = t.TABLE_NAME "
        "ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION"
    )
    tables: dict[str, dict] = {}
    for r in rows:
        key = f"{r['TABLE_SCHEMA']}.{r['TABLE_NAME']}"
        t = tables.setdefault(key, {"schema": r["TABLE_SCHEMA"], "name": r["TABLE_NAME"], "type": r["TABLE_TYPE"], "columns": []})
        t["columns"].append({"name": r["COLUMN_NAME"], "type": r["DATA_TYPE"]})
    schema = {"database": os.environ.get("SIGNAL_SQL_DATABASE", ""), "tables": list(tables.values()), "fetched_at": datetime.utcnow().isoformat() + "Z"}
    with _signal_lock:
        _signal_cache["schema"] = schema
        _signal_cache["schema_ts"] = now
    return schema


def _signal_pick(cols: list[str], hints: tuple, type_filter=None, types: dict | None = None):
    lc = {c.lower(): c for c in cols}
    for h in hints:
        for lname, orig in lc.items():
            if h in lname and (type_filter is None or (types and type_filter(types.get(orig, "")))):
                return orig
    return None


def _signal_discover_passages(schema: dict) -> dict | None:
    """Heuristically find the table that carries strait/chokepoint transits."""
    best = None
    for t in schema["tables"]:
        cols = [c["name"] for c in t["columns"]]
        types = {c["name"]: c["type"].lower() for c in t["columns"]}
        strait = _signal_pick(cols, _SIGNAL_STRAIT_HINTS)
        if not strait:
            continue
        is_date = lambda ty: ("date" in ty) or ("time" in ty)
        date_col = _signal_pick(cols, _SIGNAL_DATE_HINTS, is_date, types)
        if not date_col:
            continue
        score = 2
        name_l = t["name"].lower()
        if any(h in name_l for h in ("passage", "transit", "strait", "chokepoint")):
            score += 3
        cls = _signal_pick(cols, _SIGNAL_CLASS_HINTS)
        vessel = _signal_pick(cols, _SIGNAL_VESSEL_HINTS)
        direction = _signal_pick(cols, _SIGNAL_DIR_HINTS)
        score += (1 if cls else 0) + (1 if vessel else 0)
        cand = {"table": f"[{t['schema']}].[{t['name']}]", "table_key": f"{t['schema']}.{t['name']}", "date": date_col, "strait": strait, "class": cls, "vessel": vessel, "direction": direction, "score": score}
        if best is None or cand["score"] > best["score"]:
            best = cand
    return best


def _signal_norm_class(v) -> str:
    if v is None:
        return "Unknown"
    s = str(v).strip()
    return _SIGNAL_CLASS_ALIASES.get(s.lower(), s)


def _signal_passages(days: int, force: bool = False) -> dict:
    ck = f"passages:{days}"
    now = _time.time()
    with _signal_lock:
        ent = _signal_cache["data"].get(ck)
        if ent and not force and now - ent["ts"] < SIGNAL_DATA_TTL:
            return ent["val"]

    override = os.environ.get("SIGNAL_PASSAGES_SQL", "").strip()
    mapping = None
    if override:
        # Override must return columns: day, strait, vessel_class, passages (and optionally direction)
        rows = _signal_rows(override.replace("{days}", str(int(days))))
        recs = [{"day": str(r.get("day") or r.get("Day"))[:10], "strait": r.get("strait") or r.get("Strait"),
                 "vessel_class": _signal_norm_class(r.get("vessel_class") or r.get("VesselClass")),
                 "direction": r.get("direction"), "passages": int(r.get("passages") or r.get("Passages") or 0)} for r in rows]
        source = {"mode": "override_sql"}
    else:
        schema = _signal_schema()
        mapping = _signal_discover_passages(schema)
        if not mapping:
            val = {"available": False, "reason": "no_passages_table", "tables": [t["schema"] + "." + t["name"] for t in schema["tables"]]}
            with _signal_lock:
                _signal_cache["data"][ck] = {"ts": now, "val": val}
            return val
        d, s, c, v, dr = mapping["date"], mapping["strait"], mapping["class"], mapping["vessel"], mapping["direction"]
        cnt = f"COUNT(DISTINCT [{v}])" if v else "COUNT(*)"
        sel_cls = f"[{c}]" if c else "'All'"
        sel_dir = f"[{dr}]" if dr else "NULL"
        grp = f"CAST([{d}] AS date), [{s}]" + (f", [{c}]" if c else "") + (f", [{dr}]" if dr else "")
        sql = (
            f"SELECT CAST([{d}] AS date) AS day, [{s}] AS strait, {sel_cls} AS vessel_class, {sel_dir} AS direction, {cnt} AS passages "
            f"FROM {mapping['table']} WHERE [{d}] >= DATEADD(day, -{int(days)}, CAST(GETUTCDATE() AS date)) AND [{s}] IS NOT NULL "
            f"GROUP BY {grp} ORDER BY 1"
        )
        rows = _signal_rows(sql)
        recs = [{"day": str(r["day"])[:10], "strait": str(r["strait"]), "vessel_class": _signal_norm_class(r["vessel_class"]),
                 "direction": (str(r["direction"]) if r["direction"] is not None else None), "passages": int(r["passages"] or 0)} for r in rows]
        source = {"mode": "auto", **{k: mapping[k] for k in ("table_key", "date", "strait", "class", "vessel", "direction")}}

    # Aggregate into per-strait daily series (all classes + per class)
    import collections
    straits: dict[str, dict] = {}
    all_days = sorted({r["day"] for r in recs})
    if all_days:
        from datetime import date as _date, timedelta as _td
        d0, d1 = _date.fromisoformat(all_days[0]), _date.fromisoformat(all_days[-1])
        all_days = [(d0 + _td(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    for r in recs:
        st = straits.setdefault(r["strait"], {"total": collections.Counter(), "by_class": collections.defaultdict(collections.Counter), "by_dir": collections.defaultdict(collections.Counter)})
        st["total"][r["day"]] += r["passages"]
        st["by_class"][r["vessel_class"]][r["day"]] += r["passages"]
        if r["direction"]:
            st["by_dir"][r["direction"]][r["day"]] += r["passages"]

    def _series(counter):
        return [counter.get(dd, 0) for dd in all_days]

    def _avg(vals):
        return round(sum(vals) / len(vals), 2) if vals else None

    out_straits = []
    for name, st in straits.items():
        tot = _series(st["total"])
        last7 = _avg(tot[-7:]); prev30 = _avg(tot[-37:-7]) if len(tot) > 7 else None
        out_straits.append({
            "strait": name,
            "total": tot,
            "by_class": {k: _series(v) for k, v in st["by_class"].items()},
            "by_direction": {k: _series(v) for k, v in st["by_dir"].items()},
            "sum_period": sum(tot),
            "avg_7d": last7, "avg_30d_prior": prev30,
            "delta_7d_vs_30d_pct": (round((last7 - prev30) / prev30 * 100, 1) if last7 is not None and prev30 else None),
            "latest_day": all_days[-1] if all_days else None,
            "latest": tot[-1] if tot else None,
        })
    out_straits.sort(key=lambda x: -x["sum_period"])
    classes = sorted({r["vessel_class"] for r in recs}, key=lambda x: ["VLCC", "Suezmax", "Aframax"].index(x) if x in ("VLCC", "Suezmax", "Aframax") else 99)
    val = {"available": True, "days": days, "dates": all_days, "classes": classes, "straits": out_straits, "source": source, "rows": len(recs), "fetched_at": datetime.utcnow().isoformat() + "Z"}
    with _signal_lock:
        _signal_cache["data"][ck] = {"ts": now, "val": val}
    return val


@app.get("/api/signal/status")
async def signal_status():
    """Signal Ocean Azure SQL connectivity check."""
    server = os.environ.get("SIGNAL_SQL_SERVER", "")
    if not _signal_configured():
        return {"configured": False, "connected": False, "server": server, "message": "Set SIGNAL_SQL_SERVER, SIGNAL_SQL_USERNAME, SIGNAL_SQL_PASSWORD (and optionally SIGNAL_SQL_DATABASE)."}
    try:
        info = _signal_rows("SELECT DB_NAME() AS db, SUSER_SNAME() AS login, @@VERSION AS version")[0]
        try:
            schema = _signal_schema()
            n_tables = len(schema["tables"])
        except Exception as e:
            n_tables = None
        return {"configured": True, "connected": True, "server": server, "database": info["db"], "login": info["login"],
                "version": (info["version"] or "").split("\n")[0][:120], "tables": n_tables}
    except Exception as e:
        return {"configured": True, "connected": False, "server": server, "database": os.environ.get("SIGNAL_SQL_DATABASE", ""), "error": str(e)[:400]}


@app.get("/api/signal/schema")
async def signal_schema(refresh: bool = Query(False)):
    """List tables/columns visible to the Signal login (cached 1h)."""
    if not _signal_configured():
        return {"error": "Signal SQL not configured"}
    try:
        return _signal_schema(force=refresh)
    except Exception as e:
        return {"error": str(e)[:400]}


_SIGNAL_IDENT_RE = _re.compile(r"^[A-Za-z0-9_ .\-]+$")


@app.get("/api/signal/preview")
async def signal_preview(table: str = Query(...), limit: int = Query(50, ge=1, le=500)):
    """Read-only TOP-N preview of a table known from the schema listing."""
    if not _signal_configured():
        return {"error": "Signal SQL not configured"}
    if not _SIGNAL_IDENT_RE.match(table):
        raise HTTPException(status_code=400, detail="invalid table identifier")
    try:
        schema = _signal_schema()
        known = {f"{t['schema']}.{t['name']}": t for t in schema["tables"]}
        t = known.get(table)
        if not t:
            raise HTTPException(status_code=404, detail="unknown table")
        rows = _signal_rows(f"SELECT TOP ({int(limit)}) * FROM [{t['schema']}].[{t['name']}]")
        cnt = _signal_rows(f"SELECT COUNT_BIG(*) AS n FROM [{t['schema']}].[{t['name']}]")[0]["n"] if limit <= 100 else None
        return {"table": table, "columns": [c["name"] for c in t["columns"]], "rows": rows, "row_count": cnt}
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)[:400]}


@app.get("/api/signal/passages")
async def signal_passages(days: int = Query(90, ge=7, le=1100), refresh: bool = Query(False)):
    """Daily tanker passages (DPP Aframax/Suezmax/VLCC) through straits/chokepoints."""
    if not _signal_configured():
        return {"available": False, "reason": "not_configured"}
    try:
        return _signal_passages(days, force=refresh)
    except Exception as e:
        return {"available": False, "reason": "error", "error": str(e)[:400]}


# ============================================================
# Refinery Margins (seasonal %rank method)
# ============================================================
_MARGINS_CACHE = None

def _load_margins_raw():
    """Load parsed weekly refinery margins from the committed JSON file."""
    global _MARGINS_CACHE
    if _MARGINS_CACHE is not None:
        return _MARGINS_CACHE
    path = os.path.join(os.path.dirname(__file__), "margins_data.json")
    with open(path) as f:
        _MARGINS_CACHE = _json.load(f)
    return _MARGINS_CACHE


def _season_for(month: int) -> str:
    """Season classification: SUMMER = Mar-Aug (3-8), WINTER = Sep-Feb."""
    return "WINTER" if (month < 3 or month > 8) else "SUMMER"


def _pct_rank(sorted_vals, x):
    """Percentile rank of x within sorted_vals (0-100), like Excel PERCENTRANK.INC."""
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return 50.0
    # count strictly below and equal
    below = 0
    equal = 0
    for v in sorted_vals:
        if v < x:
            below += 1
        elif v == x:
            equal += 1
    # Excel-style: (below + 0.5*equal) / n
    return round((below + 0.5 * equal) / n * 100, 1)


@app.get("/api/margins")
async def get_margins():
    """Refinery margins with seasonal percentile-rank analysis.

    For each margin: latest value, current season, 4wk/13wk moving averages,
    trend, %rank (all-time), %rank (seasonal), winter/summer medians, BUY/SELL
    signal (seasonal %rank <10 = BUY, >90 = SELL), plus the full weekly time
    series with season tags for charting.
    """
    raw = _load_margins_raw()
    dates = raw["dates"]
    months = [int(d[5:7]) for d in dates]
    seasons = [_season_for(m) for m in months]

    results = []
    regions_order = []
    for m in raw["margins"]:
        vals = m["values"]
        # Build cleaned (date_idx, value) pairs
        clean = [(i, v) for i, v in enumerate(vals) if v is not None]
        if len(clean) < 5:
            continue
        idxs = [i for i, _ in clean]
        cvals = [v for _, v in clean]
        latest_idx = idxs[-1]
        latest = cvals[-1]
        latest_season = seasons[latest_idx]

        # Moving averages (over cleaned series)
        def _ma(n):
            if len(cvals) < n:
                seg = cvals
            else:
                seg = cvals[-n:]
            return round(float(np.mean(seg)), 3)
        ma4 = _ma(4)
        ma13 = _ma(13)
        ma52 = _ma(52)
        trend = "RISING" if ma4 >= ma13 else "FALLING"

        # %rank all-time
        rank_all = _pct_rank(sorted(cvals), latest)

        # %rank seasonal (only vs same-season history)
        season_vals = [cvals[k] for k in range(len(clean)) if seasons[idxs[k]] == latest_season]
        rank_seasonal = _pct_rank(sorted(season_vals), latest)

        # winter/summer medians
        winter_vals = [cvals[k] for k in range(len(clean)) if seasons[idxs[k]] == "WINTER"]
        summer_vals = [cvals[k] for k in range(len(clean)) if seasons[idxs[k]] == "SUMMER"]
        winter_med = round(float(np.median(winter_vals)), 3) if winter_vals else None
        summer_med = round(float(np.median(summer_vals)), 3) if summer_vals else None

        # signal from seasonal rank
        if rank_seasonal is not None and rank_seasonal < 10:
            signal = "BUY"
        elif rank_seasonal is not None and rank_seasonal > 90:
            signal = "SELL"
        else:
            signal = "NEUTRAL"

        # min/max/avg
        stats = {
            "min": round(min(cvals), 3),
            "max": round(max(cvals), 3),
            "avg": round(float(np.mean(cvals)), 3),
            "median": round(float(np.median(cvals)), 3),
            "stdev": round(float(np.std(cvals)), 3),
        }
        # z-score of latest
        zscore = round((latest - stats["avg"]) / stats["stdev"], 2) if stats["stdev"] else None

        # Full series for charts (only cleaned points)
        series_dates = [dates[i] for i in idxs]

        if m["region"] not in regions_order:
            regions_order.append(m["region"])

        results.append({
            "key": m["key"],
            "region": m["region"],
            "name": m["name"],
            "latest": round(latest, 3),
            "latest_date": dates[latest_idx],
            "season": latest_season,
            "ma4": ma4,
            "ma13": ma13,
            "ma52": ma52,
            "trend": trend,
            "rank_all": rank_all,
            "rank_seasonal": rank_seasonal,
            "winter_median": winter_med,
            "summer_median": summer_med,
            "signal": signal,
            "zscore": zscore,
            "stats": stats,
            "series_dates": series_dates,
            "series_values": [round(v, 3) for v in cvals],
            "series_seasons": [seasons[i] for i in idxs],
        })

    return {
        "as_of": dates[-1],
        "n_weeks": len(dates),
        "start_date": dates[0],
        "regions": regions_order,
        "season_definition": "SUMMER = Mar-Aug, WINTER = Sep-Feb (grade seasonality)",
        "margins": results,
    }


_CRUDE_BAL_CACHE = None


def _load_crude_balances():
    """Load parsed global crude balances / runs from the committed JSON file."""
    global _CRUDE_BAL_CACHE
    if _CRUDE_BAL_CACHE is not None:
        return _CRUDE_BAL_CACHE
    path = os.path.join(os.path.dirname(__file__), "crude_balances_data.json")
    with open(path) as f:
        _CRUDE_BAL_CACHE = _json.load(f)
    return _CRUDE_BAL_CACHE


@app.get("/api/crude-balances")
async def get_crude_balances():
    """Monthly global crude/condensate balances: regional supply, demand and
    balance; global refinery runs; supply by quality; OECD stocks; OPEC+ output;
    and the crude price outlook. Values in kb/d unless noted."""
    return _load_crude_balances()


_CRUDE_BAL_V2_CACHE = None


def _load_crude_bal_v2():
    """Load the multi-sheet Crude Balances workbook export (per-region monthly
    supply/demand/runs/balance and US PADD stocks & balances)."""
    global _CRUDE_BAL_V2_CACHE
    if _CRUDE_BAL_V2_CACHE is None:
        path = os.path.join(os.path.dirname(__file__), "crude_bal_v2.json")
        with open(path) as f:
            _CRUDE_BAL_V2_CACHE = _json.load(f)
    return _CRUDE_BAL_V2_CACHE


@app.get("/api/crude_bal_v2")
async def get_crude_bal_v2():
    """Crude Balances by sheet (Med / NW Europe / Asia / Middle East / West
    Africa / South America / Global / US). Each sheet carries monthly series
    (kb/d, mb or ratio), an ordered chart/table list, the headline series, and
    a data-driven recap+outlook. Values are model output, not investment advice."""
    return _load_crude_bal_v2()


_PRODUCT_STOCKS_CACHE = None


def _load_product_stocks():
    """Load weekly refined-product stocks by hub (Fujairah / ARA / Japan /
    Singapore), each with per-product weekly history and a data-driven recap."""
    global _PRODUCT_STOCKS_CACHE
    if _PRODUCT_STOCKS_CACHE is None:
        path = os.path.join(os.path.dirname(__file__), "product_stocks.json")
        with open(path) as f:
            _PRODUCT_STOCKS_CACHE = _json.load(f)
    return _PRODUCT_STOCKS_CACHE


@app.get("/api/product_stocks")
async def get_product_stocks():
    """Weekly refined-product stocks by hub: Fujairah, ARA, Japan (PAJ),
    Singapore (Enterprise). Each region carries per-product weekly series
    (million barrels, ARA in kt) plus a data-driven retrospective."""
    return _load_product_stocks()


_VOLOI_CACHE = None
_VOLOI_LIVE = None
_VOLOI_META = {"generated": None, "source": None}


def _voloi_live_path():
    return os.path.join(os.path.dirname(__file__), "voloi_live.json")


def _load_voloi():
    """Baseline 3-min volume/price bars (CO1/CO2/XB1/XB2/QS1/QS2) and daily OI
    (Brent/RBOB/Gasoil) shipped with the app."""
    global _VOLOI_CACHE
    if _VOLOI_CACHE is None:
        path = os.path.join(os.path.dirname(__file__), "voloi.json")
        with open(path) as f:
            _VOLOI_CACHE = _json.load(f)
    return _VOLOI_CACHE


def _get_voloi_live():
    global _VOLOI_LIVE
    if _VOLOI_LIVE is None:
        _VOLOI_LIVE = {}
        try:
            with open(_voloi_live_path()) as f:
                blob = _json.load(f)
            _VOLOI_LIVE = blob.get("data", {})
            _VOLOI_META["generated"] = blob.get("generated")
            _VOLOI_META["source"] = blob.get("source")
        except FileNotFoundError:
            pass
        except Exception:
            _VOLOI_LIVE = {}
    return _VOLOI_LIVE


@app.get("/api/voloi")
async def get_voloi():
    """Volume & OI Tracker baseline: intraday 3-min bars per contract and daily
    open-interest series per commodity. Anomaly/COT analysis is done client-side."""
    return _load_voloi()


@app.post("/api/voloi/live")
async def voloi_live_ingest(request: Request):
    """Ingest the latest 3-min volume/price bars and daily OI pushed by the local
    bridge. Auth via X-Ingest-Token in the gate. Payload: {data: {intraday, oi}}."""
    global _VOLOI_LIVE
    body = await request.json()
    if body.get("clear"):
        _VOLOI_LIVE = {}
        _VOLOI_META["generated"] = None
        _VOLOI_META["source"] = None
        try:
            os.remove(_voloi_live_path())
        except FileNotFoundError:
            pass
        return {"ok": True, "cleared": True}
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return {"ok": False, "error": "expected {data: {...}}"}
    now = datetime.utcnow().isoformat() + "Z"
    _VOLOI_LIVE = data
    _VOLOI_META["generated"] = now
    _VOLOI_META["source"] = body.get("source", "bloomberg-bridge")
    try:
        with open(_voloi_live_path(), "w") as f:
            _json.dump({"data": data, "generated": now,
                        "source": _VOLOI_META["source"]}, f)
    except Exception:
        pass
    n = len(data.get("intraday", {})) if isinstance(data, dict) else 0
    return {"ok": True, "contracts": n, "generated": now}


@app.get("/api/voloi/live")
async def voloi_live_read():
    """Return the latest live 3-min bars / OI snapshot pushed by the bridge."""
    data = _get_voloi_live()
    gen = _VOLOI_META.get("generated")
    stale = None
    if gen:
        try:
            ts = datetime.fromisoformat(gen.replace("Z", ""))
            stale = round((datetime.utcnow() - ts).total_seconds(), 1)
        except ValueError:
            stale = None
    return {"data": data, "generated": gen,
            "source": _VOLOI_META.get("source"), "stale_seconds": stale}


# ═══════════════════════════════════════════════════════════════════════════
# ═══  PLATTS / S&P GLOBAL COMMODITY INSIGHTS (SPGCI)
# ═══════════════════════════════════════════════════════════════════════════
# Server-side proxy: user credentials never reach the browser. A short-lived
# bearer token is cached in-process and refreshed automatically.

_SPGCI_BASE = "https://api.platts.com"
_SPGCI_UA = "Mozilla/5.0 (compatible; BarrelTerminal/1.0)"
_SPGCI_TOKEN_CACHE = {"token": None, "expires_at": 0.0}


def _spgci_token() -> str:
    """Return a valid SPGCI bearer token, refreshing when near expiry."""
    import time as _time
    import urllib.request as _ur
    import urllib.parse as _up
    now = _time.time()
    if _SPGCI_TOKEN_CACHE["token"] and now < _SPGCI_TOKEN_CACHE["expires_at"] - 60:
        return _SPGCI_TOKEN_CACHE["token"]
    user = os.environ.get("SPGCI_USERNAME", "")
    pw = os.environ.get("SPGCI_PASSWORD", "")
    if not user or not pw:
        raise HTTPException(status_code=503, detail="Platts credentials not configured")
    body = _up.urlencode({"username": user, "password": pw}).encode()
    req = _ur.Request(_SPGCI_BASE + "/auth/api", data=body, method="POST",
                      headers={"Content-Type": "application/x-www-form-urlencoded",
                               "User-Agent": _SPGCI_UA, "Accept": "application/json"})
    try:
        with _ur.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read().decode())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Platts auth failed: {e}")
    tok = data.get("access_token")
    if not tok:
        raise HTTPException(status_code=502, detail="Platts auth returned no token")
    _SPGCI_TOKEN_CACHE["token"] = tok
    _SPGCI_TOKEN_CACHE["expires_at"] = now + float(data.get("expires_in", 3600))
    return tok


def _spgci_get(path: str, params: dict) -> dict:
    """GET an SPGCI REST path with the cached bearer token; return parsed JSON."""
    import urllib.request as _ur
    import urllib.parse as _up
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    url = _SPGCI_BASE + path
    if clean:
        url += "?" + _up.urlencode(clean)
    tok = _spgci_token()
    req = _ur.Request(url, headers={"Authorization": f"Bearer {tok}", "Accept": "application/json",
                                    "User-Agent": _SPGCI_UA})
    try:
        with _ur.urlopen(req, timeout=45) as resp:
            return _json.loads(resp.read().decode())
    except _ur.HTTPError as e:
        detail = e.read().decode()[:300] if hasattr(e, "read") else str(e)
        raise HTTPException(status_code=e.code, detail=f"Platts API error: {detail}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Platts request failed: {e}")


@app.get("/api/platts/status")
async def platts_status():
    """Report whether Platts credentials are configured and reachable."""
    configured = bool(os.environ.get("SPGCI_USERNAME") and os.environ.get("SPGCI_PASSWORD"))
    if not configured:
        return {"configured": False, "connected": False}
    try:
        _spgci_token()
        return {"configured": True, "connected": True}
    except HTTPException as e:
        return {"configured": True, "connected": False, "detail": str(e.detail)}


@app.get("/api/platts/mdc")
async def platts_mdc(subscribed_only: bool = Query(True)):
    """List Market Data Categories (assessment groups) the account can access."""
    j = _spgci_get("/market-data/reference-data/v3/mdc",
                   {"subscribedOnly": "true" if subscribed_only else "false", "pageSize": 500})
    return {"count": j.get("metadata", {}).get("count"), "results": j.get("results", [])}


@app.get("/api/platts/search")
async def platts_search(q: str = Query(None), mdc: str = Query(None),
                        commodity: str = Query(None), page: int = Query(1),
                        page_size: int = Query(25)):
    """Search assessment symbols / reference metadata."""
    filters = []
    if mdc:
        filters.append(f'mdc: "{mdc}"')
    if commodity:
        filters.append(f'commodity: "{commodity}"')
    params = {"pageSize": page_size, "page": page}
    if q:
        params["q"] = q
    if filters:
        params["filter"] = " AND ".join(filters)
    j = _spgci_get("/market-data/reference-data/v3/search", params)
    return {"count": j.get("metadata", {}).get("count"),
            "total_pages": j.get("metadata", {}).get("total_pages"),
            "page": page, "results": j.get("results", [])}


@app.get("/api/platts/current")
async def platts_current(symbols: str = Query(...), bate: str = Query("c")):
    """Current assessment values for one or more symbols (comma-separated)."""
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    if not syms:
        raise HTTPException(status_code=400, detail="No symbols provided")
    sym_list = ",".join(f'"{s}"' for s in syms)
    filt = f"symbol IN ({sym_list})"
    if bate:
        blist = ",".join(f'"{b.strip()}"' for b in bate.split(",") if b.strip())
        filt += f" AND bate IN ({blist})"
    j = _spgci_get("/market-data/v3/value/current/symbol", {"filter": filt})
    return {"results": j.get("results", [])}


@app.get("/api/platts/history")
async def platts_history(symbol: str = Query(...), start: str = Query(None),
                         end: str = Query(None), bate: str = Query("c"),
                         page_size: int = Query(5000)):
    """Historical assessment values for a single symbol."""
    parts = [f'symbol: "{symbol}"']
    if bate:
        blist = ",".join(f'"{b.strip()}"' for b in bate.split(",") if b.strip())
        parts.append(f"bate IN ({blist})")
    if start:
        parts.append(f'assessDate >= "{start}"')
    if end:
        parts.append(f'assessDate <= "{end}"')
    j = _spgci_get("/market-data/v3/value/history/symbol",
                   {"filter": " AND ".join(parts), "pageSize": page_size})
    return {"results": j.get("results", [])}


@app.get("/api/platts/curve-search")
async def platts_curve_search(q: str = Query(None), commodity: str = Query(None),
                              page_size: int = Query(25)):
    """Search forward curves by keyword / commodity."""
    params = {"pageSize": page_size}
    if q:
        params["q"] = q
    if commodity:
        params["filter"] = f'commodity: "{commodity}"'
    j = _spgci_get("/market-data/reference-data/v3/forward-curve/search", params)
    return {"count": j.get("metadata", {}).get("count"), "results": j.get("results", [])}


@app.get("/api/platts/curve")
async def platts_curve(code: str = Query(...), page_size: int = Query(60)):
    """Forward curve contract-by-contract data for a curve code."""
    j = _spgci_get("/market-data/forward-curve/v3/curve-code",
                   {"filter": f'curve_code: "{code}"', "pageSize": page_size})
    return {"results": j.get("results", {})}


@app.get("/api/platts/news")
async def platts_news(q: str = Query(None), page_size: int = Query(20)):
    """Latest Platts news / market commentary headlines."""
    params = {"pageSize": page_size, "sort": "updatedDate:desc"}
    if q:
        params["q"] = q
    j = _spgci_get("/news-insights/v1/search", params)
    return {"count": j.get("metadata", {}).get("count"), "results": j.get("results", [])}


# --- Serve Frontend Static Files ---
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """Serve frontend static files. This must be the last route."""
    file_path = os.path.join(STATIC_DIR, full_path)
    if full_path and os.path.isfile(file_path):
        return FileResponse(file_path)
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Not found")
