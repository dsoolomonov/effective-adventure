# Sparta API Platform

A web-based platform for accessing the [Sparta Commodities API](https://documentation.sparta.app/). This application provides a secure, user-friendly interface to interact with all Sparta API endpoints.

## Features

- **Secure Authentication** — API credentials are stored server-side only; tokens are managed automatically
- **Catalogue Browser** — Search and filter available curve quotations by vertical, region, and quotation type
- **Curve Data Viewer** — Retrieve historical and current pricing curve data
- **Trade Flows** — Access commodity trade flow data across global routes
- **Price Assessments** — View price assessments for various products and markets
- **Freight Rates** — Query freight rate data for different vessel types and routes
- **Bulk Download** — Submit and track bulk data export jobs (Parquet format)
- **JSON Viewer** — Toggle between table and raw JSON views for all endpoints
- **Pagination** — Navigate through large datasets with built-in pagination

## Architecture

```
├── server/             # Express.js API proxy
│   ├── index.js        # Server entry point & route definitions
│   └── spartaApi.js    # Sparta API client with token management
├── client/             # React frontend (Vite + Tailwind CSS)
│   └── src/
│       ├── components/ # Reusable UI components
│       ├── pages/      # Page components for each endpoint
│       └── lib/        # API client utilities
└── .env.example        # Environment variable template
```

## Setup

### Prerequisites
- Node.js 18+
- A Sparta API account with API access

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd sparta-api-platform

# Install server dependencies
npm install

# Install client dependencies
cd client && npm install && cd ..

# Configure credentials
cp .env.example .env
# Edit .env with your Sparta credentials
```

### Development

```bash
# Start both server and client
npm run dev
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:3001

### Production

```bash
# Build the frontend
npm run build

# Start the production server
npm start
```

The server serves the built React app and proxies API requests.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/status` | GET | Check authentication status |
| `/api/auth/refresh` | POST | Force re-authentication |
| `/api/catalogue` | GET | Browse curve quotations |
| `/api/curve-data` | GET | Get pricing curve data |
| `/api/flows` | GET | Get trade flow data |
| `/api/assessments` | GET | Get price assessments |
| `/api/freight` | GET | Get freight rates |
| `/api/bulk-download/job-submit` | POST | Submit bulk download job |
| `/api/bulk-download/job-status/:id` | GET | Check download job status |

## Security

- API credentials are never exposed to the frontend
- All Sparta API requests are proxied through the Express server
- Bearer tokens are automatically refreshed when expired
- HTTPS is enforced for all Sparta API communication
