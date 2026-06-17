import { createSlice, PayloadAction } from '@reduxjs/toolkit';

type DashboardState = {
  widgets: Record<string, any>;
  topStocks: any[];
  loading: boolean;
  error?: string | null;
};

const initialState: DashboardState = {
  widgets: {},
  topStocks: [],
  loading: false,
  error: null,
};

const slice = createSlice({
  name: 'dashboard',
  initialState,
  reducers: {
    setWidgets(state, action: PayloadAction<Record<string, any>>) {
      state.widgets = action.payload;
    },
    setTopStocks(state, action: PayloadAction<any[]>) {
      state.topStocks = action.payload;
    },
    setLoading(state, action: PayloadAction<boolean>) {
      state.loading = action.payload;
    },
    setError(state, action: PayloadAction<string | null>) {
      state.error = action.payload;
    },
  },
});

export const { setWidgets, setTopStocks, setLoading, setError } = slice.actions;
export default slice.reducer;
