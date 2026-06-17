import { createSlice, PayloadAction } from '@reduxjs/toolkit';

type ScanState = {
  scans: any[];
  activeScanId?: string | null;
  progress: Record<string, any>;
};

const initialState: ScanState = {
  scans: [],
  activeScanId: null,
  progress: {},
};

const slice = createSlice({
  name: 'scan',
  initialState,
  reducers: {
    setScans(state, action: PayloadAction<any[]>) {
      state.scans = action.payload;
    },
    setActiveScan(state, action: PayloadAction<string | null>) {
      state.activeScanId = action.payload;
    },
    updateProgress(state, action: PayloadAction<Record<string, any>>) {
      state.progress = { ...state.progress, ...action.payload };
    },
  },
});

export const { setScans, setActiveScan, updateProgress } = slice.actions;
export default slice.reducer;
