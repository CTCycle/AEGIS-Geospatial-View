import { Routes } from '@angular/router';

import { GeospatialPageComponent } from './pages/geospatial-page.component';
import { AccessConfigurationsPageComponent } from './pages/access-configurations-page.component';
import { CapabilitiesPageComponent } from './pages/capabilities-page.component';
import { SettingsPageComponent } from './pages/settings-page.component';

export const routes: Routes = [
  { path: '', component: GeospatialPageComponent },
  { path: 'geodata', component: CapabilitiesPageComponent },
  { path: 'access-configurations', component: AccessConfigurationsPageComponent },
  { path: 'settings', component: SettingsPageComponent },
  { path: '**', redirectTo: '' },
];
