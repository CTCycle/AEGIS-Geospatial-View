import { Routes } from '@angular/router';

import { GeospatialPageComponent } from './pages/geospatial-page.component';
import { CapabilitiesPageComponent } from './pages/capabilities-page.component';
import { SettingsPageComponent } from './pages/settings-page.component';

export const routes: Routes = [
  {
    path: '',
    component: GeospatialPageComponent,
    data: {
      title: 'AEGIS | Search workspace',
      description: 'Run location-aware geospatial searches and inspect verified map results in AEGIS.',
    },
  },
  {
    path: 'geodata',
    component: CapabilitiesPageComponent,
    data: {
      title: 'AEGIS | Geospatial catalog',
      description: 'Browse the manifest-backed geospatial providers, layers, map types, and direct tools available in AEGIS.',
    },
  },
  {
    path: 'settings',
    component: SettingsPageComponent,
    data: {
      title: 'AEGIS | Settings',
      description: 'Choose the AEGIS agent model and manage model and geospatial provider access.',
    },
  },
  { path: '**', redirectTo: '' },
];
