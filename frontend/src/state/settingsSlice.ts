import { createSlice, PayloadAction } from '@reduxjs/toolkit';

type SettingsState = {
  data: Record<string, any>;
};

const initialState: SettingsState = { data: {} };

const slice = createSlice({
  name: 'settings',
  initialState,
  reducers: {
    setSettings(state, action: PayloadAction<Record<string, any>>) {
      state.data = action.payload;
    },
    updateSetting(state, action: PayloadAction<{ key: string; value: any }>) {
      state.data = { ...state.data, [action.payload.key]: action.payload.value };
    },
  },
});

export const { setSettings, updateSetting } = slice.actions;
export default slice.reducer;
