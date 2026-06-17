import { createSlice, PayloadAction } from '@reduxjs/toolkit';

type WatchlistState = {
  symbols: string[];
  alerts: any[];
};

const initialState: WatchlistState = {
  symbols: [],
  alerts: [],
};

const slice = createSlice({
  name: 'watchlist',
  initialState,
  reducers: {
    setSymbols(state, action: PayloadAction<string[]>) {
      state.symbols = action.payload;
    },
    addSymbol(state, action: PayloadAction<string>) {
      if (!state.symbols.includes(action.payload)) state.symbols.push(action.payload);
    },
    removeSymbol(state, action: PayloadAction<string>) {
      state.symbols = state.symbols.filter(s => s !== action.payload);
    },
    setAlerts(state, action: PayloadAction<any[]>) {
      state.alerts = action.payload;
    },
  },
});

export const { setSymbols, addSymbol, removeSymbol, setAlerts } = slice.actions;
export default slice.reducer;
