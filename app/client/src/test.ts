import 'zone.js/dist/zone';
import 'zone.js/dist/zone-testing';

import { getTestBed } from '@angular/core/testing';
import {
  BrowserDynamicTestingModule,
  platformBrowserDynamicTesting,
} from '@angular/platform-browser-dynamic/testing';

const originalDefineProperty = Object.defineProperty;
Object.defineProperty = function definePropertyWithConfigurable(
  object: any,
  property: PropertyKey,
  attributes: PropertyDescriptor & ThisType<any>,
): any {
  if (attributes.get && attributes.configurable === false) {
    return originalDefineProperty(object, property, {
      ...attributes,
      configurable: true,
    });
  }
  return originalDefineProperty(object, property, attributes);
};

getTestBed().initTestEnvironment(
  BrowserDynamicTestingModule,
  platformBrowserDynamicTesting(),
);
