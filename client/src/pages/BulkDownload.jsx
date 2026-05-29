import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api } from '../lib/api';
import PageHeader from '../components/PageHeader';
import ErrorMessage from '../components/ErrorMessage';
import JsonViewer from '../components/JsonViewer';
import { Download, Clock, CheckCircle2, XCircle, RefreshCw, ExternalLink } from 'lucide-react';

const VERTICALS = ['JET', 'NAPHTHA', 'ULSD', 'CRUDE', 'GASOLINE', 'FUEL_OIL'];

export default function BulkDownload() {
  const [formData, setFormData] = useState({
    startDate: '',
    endDate: '',
    vertical: '',
  });
  const [jobResult, setJobResult] = useState(null);
  const [statusResult, setStatusResult] = useState(null);
  const [pollJobId, setPollJobId] = useState('');

  const submitJob = useMutation({
    mutationFn: (params) => api.submitBulkDownload(params),
    onSuccess: (data) => {
      setJobResult(data);
      if (data.job_id) {
        setPollJobId(data.job_id);
      }
    },
  });

  const checkStatus = useMutation({
    mutationFn: (jobId) => api.getBulkDownloadStatus(jobId),
    onSuccess: (data) => {
      setStatusResult(data);
    },
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.startDate || !formData.endDate || !formData.vertical) return;
    setJobResult(null);
    setStatusResult(null);
    submitJob.mutate(formData);
  };

  const handleCheckStatus = () => {
    if (!pollJobId) return;
    checkStatus.mutate(pollJobId);
  };

  return (
    <div>
      <PageHeader
        title="Bulk Download"
        description="Submit and track bulk data export jobs. Data is exported as Parquet files partitioned by vertical, year, and month."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Submit Job */}
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h3 className="text-lg font-semibold text-slate-800 mb-4 flex items-center gap-2">
            <Download size={20} className="text-blue-500" />
            Submit Download Job
          </h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">
                Vertical
              </label>
              <select
                value={formData.vertical}
                onChange={(e) => setFormData((prev) => ({ ...prev, vertical: e.target.value }))}
                required
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select vertical...</option>
                {VERTICALS.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">
                  Start Date (YYYY-MM)
                </label>
                <input
                  type="month"
                  value={formData.startDate}
                  onChange={(e) => setFormData((prev) => ({ ...prev, startDate: e.target.value }))}
                  required
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">
                  End Date (YYYY-MM)
                </label>
                <input
                  type="month"
                  value={formData.endDate}
                  onChange={(e) => setFormData((prev) => ({ ...prev, endDate: e.target.value }))}
                  required
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={submitJob.isPending}
              className="w-full py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
            >
              {submitJob.isPending ? (
                <>
                  <RefreshCw size={16} className="animate-spin" />
                  Submitting...
                </>
              ) : (
                <>
                  <Download size={16} />
                  Submit Job
                </>
              )}
            </button>
          </form>

          {submitJob.isError && (
            <div className="mt-4">
              <ErrorMessage message={submitJob.error.message} />
            </div>
          )}

          {jobResult && (
            <div className="mt-4 bg-green-50 border border-green-200 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 size={16} className="text-green-600" />
                <span className="text-sm font-medium text-green-700">Job Submitted</span>
              </div>
              <JsonViewer data={jobResult} />
            </div>
          )}
        </div>

        {/* Check Status */}
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h3 className="text-lg font-semibold text-slate-800 mb-4 flex items-center gap-2">
            <Clock size={20} className="text-amber-500" />
            Check Job Status
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">
                Job ID
              </label>
              <input
                type="text"
                value={pollJobId}
                onChange={(e) => setPollJobId(e.target.value)}
                placeholder="Paste job ID here..."
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <button
              onClick={handleCheckStatus}
              disabled={!pollJobId || checkStatus.isPending}
              className="w-full py-2.5 bg-amber-500 text-white text-sm font-medium rounded-lg hover:bg-amber-600 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
            >
              {checkStatus.isPending ? (
                <>
                  <RefreshCw size={16} className="animate-spin" />
                  Checking...
                </>
              ) : (
                <>
                  <Clock size={16} />
                  Check Status
                </>
              )}
            </button>
          </div>

          {checkStatus.isError && (
            <div className="mt-4">
              <ErrorMessage message={checkStatus.error.message} />
            </div>
          )}

          {statusResult && (
            <div className="mt-4">
              <div className={`rounded-lg p-4 border ${
                statusResult.status === 'SUCCEEDED'
                  ? 'bg-green-50 border-green-200'
                  : statusResult.status === 'FAILED'
                  ? 'bg-red-50 border-red-200'
                  : 'bg-amber-50 border-amber-200'
              }`}>
                <div className="flex items-center gap-2 mb-3">
                  {statusResult.status === 'SUCCEEDED' ? (
                    <CheckCircle2 size={16} className="text-green-600" />
                  ) : statusResult.status === 'FAILED' ? (
                    <XCircle size={16} className="text-red-600" />
                  ) : (
                    <Clock size={16} className="text-amber-600" />
                  )}
                  <span className={`text-sm font-medium ${
                    statusResult.status === 'SUCCEEDED'
                      ? 'text-green-700'
                      : statusResult.status === 'FAILED'
                      ? 'text-red-700'
                      : 'text-amber-700'
                  }`}>
                    {statusResult.status}
                  </span>
                </div>

                {statusResult.presigned_urls && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-slate-600 mb-2">Download Links:</p>
                    {statusResult.presigned_urls.map((file, i) => (
                      <a
                        key={i}
                        href={file.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700"
                      >
                        <ExternalLink size={14} />
                        {file.path} ({(file.size / 1024 / 1024).toFixed(1)} MB)
                      </a>
                    ))}
                  </div>
                )}

                <div className="mt-3">
                  <JsonViewer data={statusResult} />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Info */}
      <div className="mt-6 bg-slate-50 border border-slate-200 rounded-xl p-6">
        <h4 className="font-semibold text-slate-700 mb-2">How Bulk Download Works</h4>
        <ol className="text-sm text-slate-600 space-y-2 list-decimal list-inside">
          <li>Select a <strong>vertical</strong> and <strong>date range</strong>, then submit the job.</li>
          <li>The API returns a <strong>job ID</strong> — copy this to track progress.</li>
          <li>Poll the <strong>job status</strong> until it shows <code className="bg-slate-200 px-1 rounded">SUCCEEDED</code>.</li>
          <li>Download files via the <strong>pre-signed URLs</strong> (valid for 1 hour).</li>
        </ol>
        <p className="text-xs text-slate-500 mt-3">
          Data is exported as Apache Parquet files, partitioned by vertical/year/month.
        </p>
      </div>
    </div>
  );
}
