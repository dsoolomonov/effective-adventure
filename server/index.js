require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');
const spartaApi = require('./spartaApi');

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

// Serve static files from React build in production
if (process.env.NODE_ENV === 'production') {
  app.use(express.static(path.join(__dirname, '..', 'client', 'dist')));
}

// Health check
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Authentication status
app.get('/api/auth/status', async (req, res) => {
  try {
    const token = await spartaApi.getToken();
    res.json({ authenticated: !!token, email: process.env.SPARTA_EMAIL });
  } catch (error) {
    res.json({ authenticated: false, error: error.message });
  }
});

// Force re-authenticate
app.post('/api/auth/refresh', async (req, res) => {
  try {
    spartaApi.clearToken();
    const token = await spartaApi.getToken();
    res.json({ success: true, authenticated: !!token });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

// Catalogue endpoint
app.get('/api/catalogue', async (req, res) => {
  try {
    const data = await spartaApi.request('/catalogue', req.query);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

// Curve data endpoint
app.get('/api/curve-data', async (req, res) => {
  try {
    const data = await spartaApi.request('/curve-data', req.query);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

// Flows endpoint
app.get('/api/flows', async (req, res) => {
  try {
    const data = await spartaApi.request('/flows', req.query);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

// Assessments endpoint
app.get('/api/assessments', async (req, res) => {
  try {
    const data = await spartaApi.request('/assessments', req.query);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

// Freight endpoint
app.get('/api/freight', async (req, res) => {
  try {
    const data = await spartaApi.request('/freight', req.query);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

// Bulk download - submit job
app.post('/api/bulk-download/job-submit', async (req, res) => {
  try {
    const data = await spartaApi.request('/bulk-download/job-submit', req.query, 'POST');
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

// Bulk download - job status
app.get('/api/bulk-download/job-status/:jobId', async (req, res) => {
  try {
    const data = await spartaApi.request(`/bulk-download/job-status/${req.params.jobId}`);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

// Generic proxy for any other Sparta API endpoint
app.all('/api/sparta/*', async (req, res) => {
  try {
    const spartaPath = req.path.replace('/api/sparta', '');
    const method = req.method;
    const data = await spartaApi.request(spartaPath, req.query, method, req.body);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

// SPA fallback for production
if (process.env.NODE_ENV === 'production') {
  app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, '..', 'client', 'dist', 'index.html'));
  });
}

app.listen(PORT, () => {
  console.log(`Sparta API Platform server running on port ${PORT}`);
});
