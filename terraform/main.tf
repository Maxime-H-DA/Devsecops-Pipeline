provider "kind" {}

resource "kind_cluster" "rpg" {
  name = "rpg-pipeline"
  wait_for_ready = true

  kind_config {
    kind = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"
    }
  }
}

provider "helm" {
    kubernetes = {
        config_path = kind_cluster.rpg.kubeconfig_path
    }
}

resource "helm_release" "kyverno" {
  name = "kyverno"
  repository = "https://kyverno.github.io/kyverno/"
  chart = "kyverno"
  version = "3.9.1"
  namespace = "kyverno"
  create_namespace = true
}

provider "kubectl" {
  config_path = kind_cluster.rpg.kubeconfig_path
  load_config_file = true
 }

 resource "kubectl_manifest" "kyverno_policies" {
  for_each = fileset("${path.module}/../policies", "*.yaml")
  yaml_body = file("${path.module}/../policies/${each.value}")
  depends_on = [helm_release.kyverno]
}


resource "helm_release" "vault" {
  name = "vault"
  repository = "https://helm.releases.hashicorp.com"
  chart = "vault"
  version = "0.34.1"
  namespace = "vault"
  create_namespace = true
  values = [file("${path.module}/../vault/vault-values.yaml")]
  wait = false
}


resource "kubectl_manifest" "rpg_namespace" {
  yaml_body = file("${path.module}/../k8s/00-namespace.yaml")
}

resource "kubectl_manifest" "rpg_pvc" {
  yaml_body = file("${path.module}/../k8s/05-pvc.yaml")
  depends_on = [kubectl_manifest.rpg_namespace]
}

resource "kubectl_manifest" "rpg_serviceaccount" {
  yaml_body = file("${path.module}/../k8s/06-serviceaccount.yaml")
  depends_on = [kubectl_manifest.rpg_namespace]
}


resource "kubectl_manifest" "rpg_deployment" {
  yaml_body = file("${path.module}/../k8s/02-deployment.yaml")
  wait_for_rollout = false
  depends_on = [
    kubectl_manifest.rpg_pvc,
    kubectl_manifest.rpg_serviceaccount,
    helm_release.vault,
  ]
}

resource "kubectl_manifest" "rpg_service" {
  yaml_body = file("${path.module}/../k8s/03-service.yaml")
  depends_on = [kubectl_manifest.rpg_namespace]
}

resource "kubectl_manifest" "rpg_networkpolicy" {
  yaml_body = file("${path.module}/../k8s/04-networkpolicy.yaml")
  depends_on = [kubectl_manifest.rpg_namespace]
}
