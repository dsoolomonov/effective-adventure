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

const VERTICALS = ['JET', 'NAPHTHA', 'ULSD', 'CRUDE', 'GASOLINE', 'FUEL_OIL'];

const filters = [
  {
    key: 'filter[vertical]',
    label: 'Vertical',
    type: 'select',
    options: VERTICALS,
  },
  { key: 'filter[region]', label: 'Region', type: 'text', placeholder: 'e.g. NWE, AG, MED' },
  { key: 'filter[quotation]', label: 'Quotation', type: 'text', placeholder: 'e.g. Delivered price by load' },
  { key: 'pageSize', label: 'Page Size', type: 'number', placeholder: '10' },
];

const columns = [
  { key: 'name', label: 'Name' },
  { key: 'units', label: 'Units' },
  {
    key: 'vertical',
    label: 'Vertical',
    render: (row) => row.filters?.vertical || '—',
  },
  {
    key: 'region',
    label: 'Region',
    render: (row) => row.filters?.region || '—',
  },
  {
    key: 'quotation',
    label: 'Quotation',
    render: (row) => row.filters?.quotation || '—',
  },
  {
    key: 'contracts',
    label: 'Contracts',
    render: (row) => row.contracts?.length || 0,
  },
];

export default function Catalogue() {
  const [filterValues, setFilterValues] = useState({ pageSize: '10' });
  const [queryParams, setQueryParams] = useState({ page: 1, pageSize: 10 });
  const [viewMode, setViewMode] = useState('table');

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['catalogue', queryParams],
    queryFn: () => api.getCatalogue(queryParams),
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
        title="Catalogue"
        description="Browse all available curve quotations. Filter by vertical, region, and quotation type."
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

      {isLoading && <LoadingSpinner message="Fetching catalogue..." />}
      {error && <ErrorMessage message={error.message} onRetry={refetch} />}

      {data && !isLoading && (
        <>
          {viewMode === 'table' ? (
            <DataTable columns={columns} data={data.items || []} />
          ) : (
            <JsonViewer data={data} />
          )}
          <Pagination
            page={queryParams.page || 1}
            onPageChange={handlePageChange}
            hasNext={!!data.next}
            hasPrev={!!data.prev}
          />
        </>
      )}
    </div>
  );
}
