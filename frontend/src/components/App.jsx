import React from "react";
import { Grommet, grommet } from "grommet";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import { deepMerge } from "grommet/utils";
import Div100vh from "react-div-100vh";

import { generateThemeChanges } from "../theme";

import { MainPage } from "../pages/MainPage";
import { DogDetailsPage } from "../pages/DogDetailsPage/DogDetailsPage";

const customTheme = deepMerge(grommet, generateThemeChanges());

function App() {
  return (
      <Grommet theme={customTheme}>
        <Div100vh className="App">
          <Router>
            <Routes>
              <Route path="/" element={<MainPage />} />
              <Route path="/dogs" element={<MainPage />} />
              <Route path="/dog/:dogId" element={<DogDetailsPage />} />
            </Routes>
          </Router>
        </Div100vh>
      </Grommet>
  );
}

export default App;