import { useEffect } from 'react';
import { useDatabaseBrowser } from '../context/DatabaseBrowserContext';
import './DatabaseBrowserPage.css';

// Refresh icon
const RefreshIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
);

// Loading spinner
const Spinner = () => (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
);

function DatabaseBrowserPage() {
    const {
        tables,
        selectedTable,
        tableData,
        isLoading,
        error,
        setSelectedTable,
        refreshData,
        loadTables,
    } = useDatabaseBrowser();

    // Load list of tables on mount (only fetches once due to context logic)
    useEffect(() => {
        loadTables();
    }, [loadTables]);

    const handleRefresh = () => {
        refreshData();
    };

    const handleTableChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
        // This will also trigger data fetch for the new table
        setSelectedTable(e.target.value);
    };

    const getDisplayName = (tableName: string): string => {
        const table = tables.find(t => t.name === tableName);
        return table?.displayName || tableName;
    };

    return (
        <div className="database-browser">
            <header className="database-header">
                <span className="breadcrumb">AEGIS DATA</span>
                <h1>Database Browser</h1>
                <p>Browse satellite layers and search history data.</p>
            </header>

            <div className="database-controls">
                <div className="table-select-group">
                    <label htmlFor="table-select">Select Table</label>
                    <div className="table-select-row">
                        <select
                            id="table-select"
                            className="table-select"
                            value={selectedTable}
                            onChange={handleTableChange}
                            disabled={isLoading}
                        >
                            {tables.map(table => (
                                <option key={table.name} value={table.name}>
                                    {table.displayName}
                                </option>
                            ))}
                        </select>
                        <button
                            className={`refresh-button ${isLoading ? 'loading' : ''}`}
                            onClick={handleRefresh}
                            disabled={isLoading || !selectedTable}
                            title="Refresh data"
                        >
                            <RefreshIcon />
                        </button>
                    </div>
                </div>

                {tableData && (
                    <div className="stats-row">
                        <div className="stat-item">
                            <span className="stat-label">Statistics</span>
                        </div>
                        <div className="stat-item">
                            <span className="stat-label">Rows:</span>
                            <span className="stat-value">{tableData.rowCount}</span>
                        </div>
                        <div className="stat-item">
                            <span className="stat-label">Columns:</span>
                            <span className="stat-value">{tableData.columnCount}</span>
                        </div>
                        <div className="stat-item">
                            <span className="stat-label">Table:</span>
                            <span className="stat-value">{getDisplayName(selectedTable)}</span>
                        </div>
                    </div>
                )}
            </div>

            <div className="data-table-container">
                {isLoading && (
                    <div className="loading-state">
                        <Spinner />
                        <span>Loading data...</span>
                    </div>
                )}

                {error && !isLoading && (
                    <div className="error-state">
                        <span>{error}</span>
                    </div>
                )}

                {!isLoading && !error && tableData && tableData.rows.length > 0 && (
                    <div className="table-scroll">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    {tableData.columns.map(col => (
                                        <th key={col}>{col.replace(/_/g, ' ')}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {tableData.rows.map((row, idx) => (
                                    <tr key={idx}>
                                        {tableData.columns.map(col => (
                                            <td key={col} title={String(row[col] ?? '')}>
                                                {row[col] !== null && row[col] !== undefined
                                                    ? String(row[col])
                                                    : ''}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {!isLoading && !error && tableData && tableData.rows.length === 0 && (
                    <div className="empty-state">
                        <span>No data available in this table.</span>
                    </div>
                )}

                {!isLoading && !error && !tableData && (
                    <div className="empty-state">
                        <span>Select a table and click the refresh button to load data.</span>
                    </div>
                )}
            </div>
        </div>
    );
}

export default DatabaseBrowserPage;
