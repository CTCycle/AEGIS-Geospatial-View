import { Routes } from '@angular/router';

import { GeospatialPageComponent } from './pages/geospatial-page.component';
import { SettingsPageComponent } from './pages/settings-page.component';

export const routes: Routes = [
  { path: '', component: GeospatialPageComponent },
  { path: 'settings', component: SettingsPageComponent },
  { path: '**', redirectTo: '' },
];
