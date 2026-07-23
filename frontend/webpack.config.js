const path = require('path');
const webpack = require('webpack');
const HtmlWebpackPlugin = require('html-webpack-plugin');

module.exports = (env, argv) => {
  const isProduction = argv.mode === 'production';

  return {
    entry: './src/index.js',
    output: {
      path: path.resolve(__dirname, 'dist'),
      filename: 'bundle.js',
      publicPath: '/',
    },
    module: {
      rules: [
        {
          test: /\.js$/,
          exclude: /node_modules/,
          use: {
            loader: 'babel-loader',
          },
        },
        {
          test: /\.css$/,
          use: ['style-loader', 'css-loader'],
        },
        {
          test: /\.png$/i,
          type: 'asset/resource',
        },
      ],
    },
    plugins: [
      new HtmlWebpackPlugin({
        template: './public/index.html',
        favicon: './public/brain.ico',
      }),
      // Inject the (public) Supabase config at build time. Unset values become
      // `undefined` and the client falls back to window.location.origin.
      new webpack.DefinePlugin({
        'process.env.SUPABASE_URL': JSON.stringify(process.env.SUPABASE_URL),
        'process.env.SUPABASE_ANON_KEY': JSON.stringify(
          process.env.SUPABASE_ANON_KEY
        ),
      }),
    ],
    // Only include devServer config in development mode
    ...(isProduction ? {} : {
      devServer: {
        static: path.join(__dirname, 'public'),
        port: 3001,
        open: true,
        historyApiFallback: true,
        hot: true, // Explicitly enable HMR only in dev
      },
    }),
  };
};
