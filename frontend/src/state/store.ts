import { configureStore } from '@reduxjs/toolkit';
import dashboardReducer from './dashboardSlice';
import scanReducer from './scanSlice';
import watchlistReducer from './watchlistSlice';
import settingsReducer from './settingsSlice';

export const store = configureStore({
  reducer: {
    dashboard: dashboardReducer,
    scan: scanReducer,
    watchlist: watchlistReducer,
    settings: settingsReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export default store;
