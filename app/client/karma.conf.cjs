module.exports = function configureKarma(config) {
  config.set({
    basePath: '',
    frameworks: ['jasmine', '@angular-devkit/build-angular'],
    plugins: [
      require('karma-jasmine'),
      require('karma-chrome-launcher'),
      require('karma-jasmine-html-reporter'),
      require('karma-coverage'),
      require('@angular-devkit/build-angular/plugins/karma'),
    ],
    client: {
      jasmine: {},
      clearContext: false,
    },
    reporters: ['progress', 'kjhtml'],
    coverageReporter: {
      dir: require('path').join(__dirname, './coverage/aegis-client'),
      subdir: '.',
      reporters: [{ type: 'html' }, { type: 'text-summary' }],
    },
    browsers: ['ChromeHeadlessNoGpu'],
    customLaunchers: {
      ChromeHeadlessNoGpu: {
        base: 'ChromeHeadless',
        flags: [
          '--disable-gpu',
          '--disable-gpu-compositing',
          '--disable-gpu-sandbox',
          '--disable-accelerated-2d-canvas',
          '--disable-accelerated-video-decode',
          '--disable-features=VizDisplayCompositor,UseSkiaRenderer',
          '--disable-webgl',
          '--disable-webgl2',
          '--disable-dev-shm-usage',
          '--disable-extensions',
          '--disable-background-networking',
          '--in-process-gpu',
          '--no-sandbox',
          '--no-first-run',
          '--no-default-browser-check',
          '--remote-debugging-port=0',
        ],
      },
    },
    restartOnFileChange: true,
  });
};
