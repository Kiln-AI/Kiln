<div class="flex flex-col items-center justify-center my-10">
  <div class="flex flex-col max-h-[500px] max-w-[500px] mt-6">
    <svg
      width="250"
      height="200"
      viewBox="75 117 350 268"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <!--
      # Animation Timeline Documentation
      
      ## Design Decisions:
      - Prompt box is static (never moves)
      - Only the width property of each line is animated
      - Animation starts at keyframe 1 layout
      
      ## Keyframe Width Values:
        Line   KF1   KF2   KF3   KF4
        1      270   242   270   269
        2      234   257   242   242
        3      260   270   232   223
        4      242   257   253   264
        5      213   143   198   242
      
      ## Timeline (6s total, loops indefinitely):
      - 0s-1s:     Hold keyframe 1 (0% - 16.67%)
      - 1s-1.5s:   Transition KF1 → KF2 (16.67% - 25%)
      - 1.5s-2.5s: Hold keyframe 2 (25% - 41.67%)
      - 2.5s-3s:   Transition KF2 → KF3 (41.67% - 50%)
      - 3s-4s:     Hold keyframe 3 (50% - 66.67%)
      - 4s-4.5s:   Transition KF3 → KF4 (66.67% - 75%)
      - 4.5s-5.5s: Hold keyframe 4 (75% - 91.67%)
      - 5.5s-6s:   Transition KF4 → KF1 (91.67% - 100%)
      
      ## keyTimes: 0;0.16667;0.25;0.41667;0.5;0.66667;0.75;0.91667;1
      ## Values pattern: KF1;KF1;KF2;KF2;KF3;KF3;KF4;KF4;KF1
      -->

      <!-- Prompt Box (static) -->
      <rect
        x="89"
        y="129"
        width="322"
        height="242"
        rx="10"
        fill="white"
        stroke="#415CF5"
        stroke-width="3"
      />

      <!-- Line 1 Text Placeholder -->
      <rect x="115" y="158" width="270" height="19" fill="#CCCCCC">
        <animate
          attributeName="width"
          dur="6s"
          repeatCount="indefinite"
          keyTimes="0;0.16667;0.25;0.41667;0.5;0.66667;0.75;0.91667;1"
          values="270;270;242;242;270;270;269;269;270"
          calcMode="linear"
        />
      </rect>

      <!-- Line 2 Text Placeholder -->
      <rect x="115" y="193" width="234" height="19" fill="#CCCCCC">
        <animate
          attributeName="width"
          dur="6s"
          repeatCount="indefinite"
          keyTimes="0;0.16667;0.25;0.41667;0.5;0.66667;0.75;0.91667;1"
          values="234;234;257;257;242;242;242;242;234"
          calcMode="linear"
        />
      </rect>

      <!-- Line 3 Text Placeholder -->
      <rect x="115" y="228" width="260" height="19" fill="#CCCCCC">
        <animate
          attributeName="width"
          dur="6s"
          repeatCount="indefinite"
          keyTimes="0;0.16667;0.25;0.41667;0.5;0.66667;0.75;0.91667;1"
          values="260;260;270;270;232;232;223;223;260"
          calcMode="linear"
        />
      </rect>

      <!-- Line 4 Text Placeholder -->
      <rect x="115" y="263" width="242" height="19" fill="#CCCCCC">
        <animate
          attributeName="width"
          dur="6s"
          repeatCount="indefinite"
          keyTimes="0;0.16667;0.25;0.41667;0.5;0.66667;0.75;0.91667;1"
          values="242;242;257;257;253;253;264;264;242"
          calcMode="linear"
        />
      </rect>

      <!-- Line 5 Text Placeholder -->
      <rect x="115" y="298" width="213" height="19" fill="#CCCCCC">
        <animate
          attributeName="width"
          dur="6s"
          repeatCount="indefinite"
          keyTimes="0;0.16667;0.25;0.41667;0.5;0.66667;0.75;0.91667;1"
          values="213;213;143;143;198;198;242;242;213"
          calcMode="linear"
        />
      </rect>
    </svg>
  </div>
  <div class="font-medium text-lg text-center mt-2">Refining Spec</div>
  <div class="font-light text-center text-gray-500 max-w-md mt-2 text-balance">
    Kiln is refining your spec with the feedback you provided. Hold tight!
  </div>
</div>
