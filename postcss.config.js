module.exports = {
  plugins: {
    'postcss-import': {},
    cssnano: {
      preset: 'default',
      discardComments: { removeAll: true },
      normalizeWhitespace: true,
      minifyFontValues: true,
      minifyGradients: true,
      minifyParams: true,
      minifySelectors: true,
      reduceIdents: false,
      zindex: false,
      // Preserve CSS custom properties
      cssDeclarationSorter: false,
    },
  },
};