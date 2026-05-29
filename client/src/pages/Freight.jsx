import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import PageHeader from '../components/PageHeader';
import FilterBar from '../components/FilterBar';
import DataTable from '../components/DataTable';
import Pagination from '../components/Pagination';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorMessage from '../components/ErrorMessage';
import JsonViewer from '../components/JsonViewer';
import { Table, Code } from 'lucide-react';

const filters = [
  { key: 'vessel', label: 'Vessel Type', type: 'text', placeholder: 'e.g. LR2, MR, VLCC' },
  { key: 'loadPort', label: 'Load Port', type: 'text', placeholder: 'e.g. RAS LAFFAN' },
  { key: 'dischargePort', label: 'Discharge Port', type: 'text', placeholder: 'e.g. BARCELONA' },
  { key: 'startDate', label: 'Start Date', type: 'date' },
  { key: 'endDate', label: 'End Date', type: 'date' },
  { key: 'pageSize', label: 'Page Size', type: 'number', placeholder: '25' },
];

const columns = [
  { key: 'name', label: 'Route Name' },
  { key: 'vessel', label: 'Vessel' },
  { key: 'loadPort', label: 'Load Port' },
  { key: 'dischargePort', label: 'Discharge Port' },
  { key: 'rate', label: 'Rate', render: (row) => row.rate != null ? Number(row.rate).toFixed(2) : '—' },
  { key: 'units', label: 'Units' },
  { key: 'date', label: 'Date' },
];

export default function Freight() {
  const [filterValues, setFilterValues] = useState({ pageSize: '25' });
  const [queryParams, setQueryParams] = useState(null);
  const [viewMode, setViewMode] = useState('table');

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['freight', queryParams],
    queryFn: () => api.getFreight(queryParams),
    enabled: !!queryParams,
  });

  const handleFilterChange = (key, value) => {
    setFilterValues((prev) => ({ ...prev, [key]: value }));
  };

  const handleSearch = () => {
    const params = { page: 1 };
    for (const [key, value] of Object.entries(filterValues)) {
      if (value) params[key] = value;
    }
    setQueryParams(params);
  };

  const handlePageChange = (newPage) => {
    setQueryParams((prev) => ({ ...prev, page: newPage }));
  };

  return (
    <div>
      <PageHeader
        title="Freight"
        description="Query freight rate data for different vessel types and shipping routes."
      >
        <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
          <button
            onClick={() => setViewMode('table')}
            className={`p-2 rounded-md transition-colors ${viewMode === 'table' ? 'bg-white shadow-sm' : 'hover:bg-slate-200'}`}
          >
            <Table size={16} />
          </button>
          <button
            onClick={() => setViewMode('json')}
            className={`p-2 rounded-md transition-colors ${viewMode === 'json' ? 'bg-white shadow-sm' : 'hover:bg-slate-200'}`}
          >
            <Code size={16} />
          </button>
        </div>
      </PageHeader>

      <FilterBar
        filters={filters}
        values={filterValues}
        onChange={handleFilterChange}
        onSubmit={handleSearch}
      />

      {!queryParams && !isLoading && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-6 text-center">
          <p className="text-blue-700 font-medium">Set your filters and click Search</p>
          <p className="text-blue-500 text-sm mt-1">
            Filter by vessel type, ports, and date range
          </p>
        </div>
      )}

      {isLoading && <LoadingSpinner message="Fetching freight data..." />}
      {error && <ErrorMessage message={error.message} onRetry={refetch} />}

      {data && !isLoading && (
        <>
          {viewMode === 'table' ? (
            <DataTable columns={columns} data={data.items || (Array.isArray(data) ? data : [])} />
          ) : (
            <JsonViewer data={data} />
          )}
          {data.next !== undefined && (
            <Pagination
              page={queryParams?.page || 1}
              onPageChange={handlePageChange}
              hasNext={!!data.next}
              hasPrev={!!data.prev}
            />
          )}
        </>
      )}
    </div>
  );
}
