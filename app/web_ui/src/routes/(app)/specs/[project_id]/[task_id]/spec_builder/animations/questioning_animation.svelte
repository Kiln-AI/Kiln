<div class="flex flex-col items-center justify-center">
  <div class="flex flex-col max-h-[250px] max-w-[250px] mt-6">
    <svg
      width="250"
      height="250"
      viewBox="0 0 600 900"
      xmlns="http://www.w3.org/2000/svg"
    >
      <!--
    ================================================================================
    ANIMATION TIMELINE DOCUMENTATION
    ================================================================================
  
    STRUCTURE:
      One main outer frame surrounding 3 component groups stacked vertically.
      Each component group contains:
      - top-bar           : Horizontal bar at top
      - content-panel     : Left-aligned main content panel
      - connector-1/2/3   : Circle connectors between panels
      - right-panel-1/2/3 : Right-side panels
  
    ANIMATION SEQUENCE:
      Main outer frame is visible from the start (static).
      Each container completes before the next begins.
      All phases are 500ms apart.
      Each element uses a POP/GROW animation (scales to 1.15 then settles to 1).
      
      Container 1: 0ms - 1500ms
        - Phase 0 (top-bar):                       0ms
        - Phase 1 (content-panel):                 500ms
        - Phase 2 (all connectors + all panels):  1000ms
      
      Container 2: 1500ms - 3000ms
        - Phase 0: 1500ms
        - Phase 1: 2000ms
        - Phase 2: 2500ms
      
      Container 3: 3000ms - 4500ms
        - Phase 0: 3000ms
        - Phase 1: 3500ms
        - Phase 2: 4000ms
  
    Total Cycle Duration: 5000ms (5 seconds) - LOOPS INFINITELY
    
    Cycle breakdown:
      0-76%:   Elements appear in sequence
      76-84%:  Hold (all visible)
      84-90%:  All elements fade out together
      90-100%: Hold invisible before restart
    ================================================================================
    -->

      <defs>
        <style>
          .stroke-primary {
            stroke: #4361ee;
            stroke-width: 2;
            fill: none;
          }

          .fill-grey {
            fill: #e0e0e0;
            stroke: none;
          }

          /* 
          LOOPING ANIMATION - 4 second cycle
          Container 1 visible on initial load, others cascade in
          Timeline: C1 visible → C2/C3 appear → hold → fade out → pause → repeat
        */

          /* Container 1: Starts visible, fades out with others, fades back in before loop */
          @keyframes container1 {
            0% {
              opacity: 1;
              transform: scale(1);
            }
            70% {
              opacity: 1;
              transform: scale(1);
            }
            80% {
              opacity: 0;
              transform: scale(0.85);
            }
            90% {
              opacity: 0;
              transform: scale(0.85);
            }
            100% {
              opacity: 1;
              transform: scale(1);
            }
          }

          /* Container 2: appears at 8% */
          @keyframes container2 {
            0%,
            8%,
            100% {
              opacity: 0;
              transform: scale(0.85);
            }
            18% {
              opacity: 1;
              transform: scale(1);
            }
            70% {
              opacity: 1;
              transform: scale(1);
            }
            80% {
              opacity: 0;
              transform: scale(0.85);
            }
          }

          /* Container 3: appears at 15% */
          @keyframes container3 {
            0%,
            15%,
            100% {
              opacity: 0;
              transform: scale(0.85);
            }
            25% {
              opacity: 1;
              transform: scale(1);
            }
            70% {
              opacity: 1;
              transform: scale(1);
            }
            80% {
              opacity: 0;
              transform: scale(0.85);
            }
          }

          /* ========== CONTAINER 1 - Visible on initial load ========== */
          #c1-top-bar,
          #c1-content-panel,
          #c1-connector-1,
          #c1-connector-2,
          #c1-connector-3,
          #c1-right-panel-1,
          #c1-right-panel-2,
          #c1-right-panel-3 {
            opacity: 1;
            transform-box: fill-box;
            transform-origin: center;
            animation: container1 4s ease-out infinite;
          }

          /* ========== CONTAINER 2 - All elements animate together ========== */
          #c2-top-bar,
          #c2-content-panel,
          #c2-connector-1,
          #c2-connector-2,
          #c2-connector-3,
          #c2-right-panel-1,
          #c2-right-panel-2,
          #c2-right-panel-3 {
            opacity: 0;
            transform-box: fill-box;
            transform-origin: center;
            animation: container2 4s ease-out infinite;
          }

          /* ========== CONTAINER 3 - All elements animate together ========== */
          #c3-top-bar,
          #c3-content-panel,
          #c3-connector-1,
          #c3-connector-2,
          #c3-connector-3,
          #c3-right-panel-1,
          #c3-right-panel-2,
          #c3-right-panel-3 {
            opacity: 0;
            transform-box: fill-box;
            transform-origin: center;
            animation: container3 4s ease-out infinite;
          }
        </style>
      </defs>

      <!-- ==================== MAIN OUTER FRAME ==================== -->
      <rect
        id="main-outer-container"
        x="50"
        y="30"
        width="500"
        height="840"
        rx="20"
        ry="20"
        class="stroke-primary"
      />

      <!-- ==================== CONTAINER 1 ==================== -->
      <g id="container-1">
        <!-- Top bar -->
        <rect
          id="c1-top-bar"
          x="75"
          y="55"
          width="450"
          height="35"
          rx="8"
          ry="8"
          class="fill-grey"
        />

        <!-- Content panel (left) -->
        <rect
          id="c1-content-panel"
          x="75"
          y="110"
          width="220"
          height="175"
          rx="4"
          ry="4"
          class="fill-grey"
        />

        <!-- Connector 1 + Right panel 1 -->
        <circle id="c1-connector-1" cx="318" cy="140" r="8" class="fill-grey" />
        <rect
          id="c1-right-panel-1"
          x="340"
          y="115"
          width="180"
          height="50"
          rx="4"
          ry="4"
          class="fill-grey"
        />

        <!-- Connector 2 + Right panel 2 -->
        <circle id="c1-connector-2" cx="318" cy="200" r="8" class="fill-grey" />
        <rect
          id="c1-right-panel-2"
          x="340"
          y="175"
          width="180"
          height="50"
          rx="4"
          ry="4"
          class="fill-grey"
        />

        <!-- Connector 3 + Right panel 3 -->
        <circle id="c1-connector-3" cx="318" cy="260" r="8" class="fill-grey" />
        <rect
          id="c1-right-panel-3"
          x="340"
          y="235"
          width="180"
          height="50"
          rx="4"
          ry="4"
          class="fill-grey"
        />
      </g>

      <!-- ==================== CONTAINER 2 ==================== -->
      <g id="container-2">
        <!-- Top bar -->
        <rect
          id="c2-top-bar"
          x="75"
          y="330"
          width="450"
          height="35"
          rx="8"
          ry="8"
          class="fill-grey"
        />

        <!-- Content panel (left) -->
        <rect
          id="c2-content-panel"
          x="75"
          y="385"
          width="220"
          height="175"
          rx="4"
          ry="4"
          class="fill-grey"
        />

        <!-- Connector 1 + Right panel 1 -->
        <circle id="c2-connector-1" cx="318" cy="415" r="8" class="fill-grey" />
        <rect
          id="c2-right-panel-1"
          x="340"
          y="390"
          width="180"
          height="50"
          rx="4"
          ry="4"
          class="fill-grey"
        />

        <!-- Connector 2 + Right panel 2 -->
        <circle id="c2-connector-2" cx="318" cy="475" r="8" class="fill-grey" />
        <rect
          id="c2-right-panel-2"
          x="340"
          y="450"
          width="180"
          height="50"
          rx="4"
          ry="4"
          class="fill-grey"
        />

        <!-- Connector 3 + Right panel 3 -->
        <circle id="c2-connector-3" cx="318" cy="535" r="8" class="fill-grey" />
        <rect
          id="c2-right-panel-3"
          x="340"
          y="510"
          width="180"
          height="50"
          rx="4"
          ry="4"
          class="fill-grey"
        />
      </g>

      <!-- ==================== CONTAINER 3 ==================== -->
      <g id="container-3">
        <!-- Top bar -->
        <rect
          id="c3-top-bar"
          x="75"
          y="605"
          width="450"
          height="35"
          rx="8"
          ry="8"
          class="fill-grey"
        />

        <!-- Content panel (left) -->
        <rect
          id="c3-content-panel"
          x="75"
          y="660"
          width="220"
          height="175"
          rx="4"
          ry="4"
          class="fill-grey"
        />

        <!-- Connector 1 + Right panel 1 -->
        <circle id="c3-connector-1" cx="318" cy="690" r="8" class="fill-grey" />
        <rect
          id="c3-right-panel-1"
          x="340"
          y="665"
          width="180"
          height="50"
          rx="4"
          ry="4"
          class="fill-grey"
        />

        <!-- Connector 2 + Right panel 2 -->
        <circle id="c3-connector-2" cx="318" cy="750" r="8" class="fill-grey" />
        <rect
          id="c3-right-panel-2"
          x="340"
          y="725"
          width="180"
          height="50"
          rx="4"
          ry="4"
          class="fill-grey"
        />

        <!-- Connector 3 + Right panel 3 -->
        <circle id="c3-connector-3" cx="318" cy="810" r="8" class="fill-grey" />
        <rect
          id="c3-right-panel-3"
          x="340"
          y="785"
          width="180"
          height="50"
          rx="4"
          ry="4"
          class="fill-grey"
        />
      </g>
    </svg>
  </div>
  <div class="font-medium text-lg text-center mt-2">
    Preparing Clarifying Questions
  </div>
  <div class="font-light text-center text-gray-500 max-w-md mt-2 text-balance">
    Kiln is analyzing your spec to identify areas that could use more clarity.
  </div>
</div>
