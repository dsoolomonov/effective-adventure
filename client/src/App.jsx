import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Catalogue from './pages/Catalogue';
import CurveData from './pages/CurveData';
import Flows from './pages/Flows';
import Assessments from './pages/Assessments';
import Freight from './pages/Freight';
import BulkDownload from './pages/BulkDownload';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 60000,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="catalogue" element={<Catalogue />} />
            <Route path="curve-data" element={<CurveData />} />
            <Route path="flows" element={<Flows />} />
            <Route path="assessments" element={<Assessments />} />
            <Route path="freight" element={<Freight />} />
            <Route path="bulk-download" element={<BulkDownload />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
