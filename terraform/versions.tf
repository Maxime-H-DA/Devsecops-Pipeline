terraform {
  required_version = ">= 1.6"

  required_providers {
    kind = {
      source = "tehcyx/kind"
      version = "~> 0.11"
    }

    helm = {
        source = "hashicorp/helm"
        version = "~> 3.2"
    }

    kubectl ={
      source = "alekc/kubectl"
      version = "~> 2.1"
    }
  }
}
