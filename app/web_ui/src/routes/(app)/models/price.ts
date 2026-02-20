export interface PricingModel {
  input_price?: number
  output_price?: number
}

interface PricingCost {
  input?: number
  output?: number
}

interface ServerModel {
  cost: PricingCost
}

export interface PricingProvider {
  models: Record<string, ServerModel>
}

export interface PricingData {
  [provider: string]: PricingProvider
}

let pricingData: PricingData | null = null
let pricingLoadPromise: Promise<PricingData | null> | null = null

export async function fetchPricingData(): Promise<PricingData | null> {
  if (pricingLoadPromise) {
    return pricingLoadPromise
  }

  pricingLoadPromise = (async () => {
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 5000)

      const response = await fetch("https://models.dev/api.json", {
        signal: controller.signal,
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        return null
      }

      const data: unknown = await response.json()

      // Validate the data structure is safe to use
      if (typeof data === "object" && data !== null) {
        pricingData = data as PricingData
        return pricingData
      }

      return null
    } catch {
      return null
    }
  })()

  return pricingLoadPromise
}

export function getModelPrice(
  providerName: string,
  modelName: string,
): { inputPrice: number | null; outputPrice: number | null } {
  // Ollama is free to use
  if (providerName === "ollama") {
    return { inputPrice: null, outputPrice: null }
  }

  if (!pricingData) {
    return { inputPrice: null, outputPrice: null }
  }

  const provider = pricingData[providerName]
  if (!provider || !provider.models) {
    return { inputPrice: null, outputPrice: null }
  }

  const model = provider.models[modelName]
  if (!model) {
    return { inputPrice: null, outputPrice: null }
  }

  return {
    inputPrice: validatePrice(model.cost?.input),
    outputPrice: validatePrice(model.cost?.output),
  }
}

function validatePrice(price: any): number | null {
  if (typeof price === "number" && isFinite(price)) {
    return price
  }
  return null
}
