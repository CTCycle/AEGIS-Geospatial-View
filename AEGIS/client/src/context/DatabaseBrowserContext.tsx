import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { fetchTables, fetchTableData, TableInfo, TableData } from '../services/api';

interface DatabaseBrowserState {
    tables: TableInfo[];
    selectedTable: string;
    tableData: TableData | null;
    isLoading: boolean;
    error: string | null;
}

interface DatabaseBrowserContextType extends DatabaseBrowserState {
    setSelectedTable: (tableName: string) => void;
    refreshData: () => void;
    loadTables: () => void;
}

const DatabaseBrowserContext = createContext<DatabaseBrowserContextType | null>(null);

export function DatabaseBrowserProvider({ children }: Readonly<{ children: ReactNode }>) {
    const [tables, setTables] = useState<TableInfo[]>([]);
    const [selectedTable, setSelectedTable] = useState<string>('');
    const [tableData, setTableData] = useState<TableData | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [tablesLoaded, setTablesLoaded] = useState(false);

    // Load list of tables (only once)
    const loadTables = useCallback(async () => {
        if (tablesLoaded) return;
        try {
            const data = await fetchTables();
            setTables(data);
            if (data.length > 0 && !selectedTable) {
                setSelectedTable(data[0].name);
            }
            setTablesLoaded(true);
        } catch (err) {
            setError('Failed to load tables');
            console.error(err);
        }
    }, [tablesLoaded, selectedTable]);

    // Load table data for the given table
    const loadTableData = useCallback(async (tableName: string) => {
        if (!tableName) return;
        setIsLoading(true);
        setError(null);
        try {
            const data = await fetchTableData(tableName);
            setTableData(data);
        } catch (err) {
            setError('Failed to load table data');
            console.error(err);
        } finally {
            setIsLoading(false);
        }
    }, []);

    // Handle table selection change - fetch data for new table
    const handleSelectedTableChange = useCallback((tableName: string) => {
        setSelectedTable(tableName);
        // Fetch data when selecting a different table
        loadTableData(tableName);
    }, [loadTableData]);

    // Refresh current table data
    const refreshData = useCallback(() => {
        if (selectedTable) {
            loadTableData(selectedTable);
        }
    }, [selectedTable, loadTableData]);

    return (
        <DatabaseBrowserContext.Provider
            value={{
                tables,
                selectedTable,
                tableData,
                isLoading,
                error,
                setSelectedTable: handleSelectedTableChange,
                refreshData,
                loadTables,
            }}
        >
            {children}
        </DatabaseBrowserContext.Provider>
    );
}

export function useDatabaseBrowser() {
    const context = useContext(DatabaseBrowserContext);
    if (!context) {
        throw new Error('useDatabaseBrowser must be used within a DatabaseBrowserProvider');
    }
    return context;
}
