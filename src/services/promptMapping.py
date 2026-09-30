
from src.agents.prompts import (webFunctionalTestCasePrompt,
                                webIntegrationTestCasePrompt,
                                webE2eTestCasePrompt,
                                webEdgeCaseTestCasePrompt,
                                mobileFunctionalTestCasePrompt,
                                mobileIntegrationTestCasePrompt,
                                mobileE2eTestCasePrompt,
                                mobileEdgeCaseTestCasePrompt,
                                iosFunctionalTestCasePrompt,
                                iosIntegrationTestCasePrompt,
                                iosE2eTestCasePrompt,
                                iosEdgeCaseTestCasePrompt,
                                ImagewebFunctionalTestCasePrompt,
                                ImagewebIntegrationTestCasePrompt,
                                ImagewebEdgeCaseTestCasePrompt,
                                ImagewebE2eTestCasePrompt,
                                ImagemobileFunctionalTestCasePrompt,
                                ImagemobileIntegrationTestCasePrompt,
                                ImagemobileEdgeCaseTestCasePrompt,
                                ImagemobileE2eTestCasePrompt,
                                ImageIosFunctionalTestCasePrompt,
                                ImageIosIntegrationTestCasePrompt,
                                ImageIosEdgeCaseTestCasePrompt,
                                ImageIosE2eTestCasePrompt,
                                FilewebFunctionalTestCasePrompt,
                                FilewebEdgeCaseTestCasePrompt,
                                FilewebIntegrationTestCasePrompt,
                                FilewebE2eTestCasePrompt,
                                FilemobileFunctionalTestCasePrompt,
                                FilemobileEdgeCaseTestCasePrompt,
                                FilemobileIntegrationTestCasePrompt,
                                FilemobileE2eTestCasePrompt,
                                FileiosFunctionalTestCasePrompt,
                                FileiosIntegrationTestCasePrompt,
                                FileiosE2eTestCasePrompt,
                                FileiosEdgeCaseTestCasePrompt,
                                VideoProcessWebFunctionalTestCasePrompt,
                                VideoProcessWebIntegrationTestCasePrompt,
                                VideoProcessWebEdgeCaseTestCasePrompt,
                                VideoProcessWebE2eTestCasePrompt,
                                VideoProcessmobileFunctionalTestCasePrompt,
                                VideoProcessmobileIntegrationTestCasePrompt,
                                VideoProcessmobileEdgeCaseTestCasePrompt,
                                VideoProcessmobileE2eTestCasePrompt,
                                VideoProcessiosFunctionalTestCasePrompt,
                                VideoProcessiosIntegrationTestCasePrompt,
                                VideoProcessiosedgeCaseTestCasePrompt,
                                VideoProcessiosE2eTestCasePrompt,
                                FigmawebFunctionalTestCasePrompt,
                                FigmawebEdgeCaseTestCasePrompt,
                                FigmawebIntegrationTestCasePrompt,
                                FigmawebE2eTestCasePrompt,
                                FigmamobileFunctionalTestCasePrompt,
                                FigmamobileEdgeCaseTestCasePrompt,
                                FigmamobileIntegrationTestCasePrompt,
                                FigmamobileE2eTestCasePrompt,
                                FigmaiosFunctionalTestCasePrompt,
                                FigmaiosEdgeCaseTestCasePrompt,
                                FigmaiosIntegrationTestCasePrompt,
                                FigmaiosE2eTestCasePrompt,
                                GenericWebFunctionalTestCasePrompt,
                                GenericWebEdgeCaseTestCasePrompt,
                                GenericWebIntegrationTestCasePrompt,
                                GenericWebE2eTestCasePrompt,
                                GenericMobileFunctionalTestCasePrompt,
                                GenericMobileEdgeCaseTestCasePrompt,
                                GenericMobileIntegrationTestCasePrompt,
                                GenericMobileE2eTestCasePrompt,
                                GenericIosFunctionalTestCasePrompt,
                                GenericIosEdgeCaseTestCasePrompt,
                                GenericIosIntegrationTestCasePrompt,
                                GenericIosE2eTestCasePrompt)

from src.integrations.jira.prompts import (jira_web_functional_mtc_generation,
                                            jira_web_integration_mtc_generation,
                                            jira_web_e2e_mtc_generation,
                                            jira_web_edge_mtc_generation,
                                            jira_mobile_functional_mtc_generation,
                                            jira_mobile_integration_mtc_generation,
                                            jira_mobile_e2e_mtc_generation,
                                            jira_mobile_edge_mtc_generation,
                                            jira_ios_functional_mtc_generation,
                                            jira_ios_integration_mtc_generation,
                                            jira_ios_e2e_mtc_generation,
                                            jira_ios_edge_mtc_generation)

class PromptRouter:
    def __init__(self, json_template,serviceProvider,is_image,is_file,is_video,is_figma,is_jira):
        self.json_template = json_template
        self.service_provider=serviceProvider
        if is_image:
            self.handlers_web = {
            "functional": ImagewebFunctionalTestCasePrompt,
            "edge": ImagewebEdgeCaseTestCasePrompt,
            "integration": ImagewebIntegrationTestCasePrompt,
            "e2e": ImagewebE2eTestCasePrompt
            }
            self.handler_mobile = {
                "functional": ImagemobileFunctionalTestCasePrompt,
                "edge": ImagemobileEdgeCaseTestCasePrompt,
                "integration": ImagemobileIntegrationTestCasePrompt,
                "e2e": ImagemobileE2eTestCasePrompt
            }
            self.handler_ios = {
                "functional": ImageIosFunctionalTestCasePrompt,
                "edge": ImageIosEdgeCaseTestCasePrompt,
                "integration": ImageIosIntegrationTestCasePrompt,
                "e2e": ImageIosE2eTestCasePrompt
            }

        elif is_file:
            self.handlers_web = {
            "functional": FilewebFunctionalTestCasePrompt,
            "edge": FilewebEdgeCaseTestCasePrompt,
            "integration": FilewebIntegrationTestCasePrompt,
            "e2e": FilewebE2eTestCasePrompt
            }
            self.handler_mobile = {
                "functional": FilemobileFunctionalTestCasePrompt,
                "edge": FilemobileEdgeCaseTestCasePrompt,
                "integration": FilemobileIntegrationTestCasePrompt,
                "e2e": FilemobileE2eTestCasePrompt
            }

            self.handler_ios = {
                "functional": FileiosFunctionalTestCasePrompt,
                "edge": FileiosEdgeCaseTestCasePrompt,
                "integration": FileiosIntegrationTestCasePrompt,
                "e2e": FileiosE2eTestCasePrompt
            }

        elif is_video:
            self.handlers_web = {
            "functional": VideoProcessWebFunctionalTestCasePrompt,
            "edge": VideoProcessWebEdgeCaseTestCasePrompt,
            "integration": VideoProcessWebIntegrationTestCasePrompt,
            "e2e": VideoProcessWebE2eTestCasePrompt
            }
            self.handler_mobile = {
                "functional": VideoProcessmobileFunctionalTestCasePrompt,
                "edge": VideoProcessmobileEdgeCaseTestCasePrompt,
                "integration": VideoProcessmobileIntegrationTestCasePrompt,
                "e2e": VideoProcessmobileE2eTestCasePrompt
            }
            self.handler_ios = {
                "functional": VideoProcessiosFunctionalTestCasePrompt,
                "edge": VideoProcessiosedgeCaseTestCasePrompt,
                "integration": VideoProcessiosIntegrationTestCasePrompt,
                "e2e": VideoProcessiosE2eTestCasePrompt
            }

        elif is_figma:
            self.handlers_web = {
            "functional": FigmawebFunctionalTestCasePrompt,
            "edge": FigmawebEdgeCaseTestCasePrompt,
            "integration": FigmawebIntegrationTestCasePrompt,
            "e2e": FigmawebE2eTestCasePrompt
            }
            self.handler_mobile = {
                "functional": FigmamobileFunctionalTestCasePrompt,
                "edge": FigmamobileEdgeCaseTestCasePrompt,
                "integration": FigmamobileIntegrationTestCasePrompt,
                "e2e": FigmamobileE2eTestCasePrompt
            }
            self.handler_ios = {
                "functional": FigmaiosFunctionalTestCasePrompt,
                "edge": FigmaiosEdgeCaseTestCasePrompt,
                "integration": FigmaiosIntegrationTestCasePrompt,
                "e2e": FigmaiosE2eTestCasePrompt
            } 

        elif is_jira:
            self.handlers_web = {
                "functional": jira_web_functional_mtc_generation,
                "edge": jira_web_edge_mtc_generation,
                "integration": jira_web_integration_mtc_generation,
                "e2e": jira_web_e2e_mtc_generation
            }
            self.handler_mobile = {
                "functional": jira_mobile_functional_mtc_generation,
                "edge": jira_mobile_edge_mtc_generation,
                "integration": jira_mobile_integration_mtc_generation,
                "e2e": jira_mobile_e2e_mtc_generation
            }
            self.handler_ios = {
                "functional": jira_ios_functional_mtc_generation,
                "edge": jira_ios_edge_mtc_generation,
                "integration": jira_ios_integration_mtc_generation,
                "e2e": jira_ios_e2e_mtc_generation
            }
        else:
            self.handlers_web = {
                "functional": webFunctionalTestCasePrompt,
                "edge": webEdgeCaseTestCasePrompt,
                "integration": webIntegrationTestCasePrompt,
                "e2e": webE2eTestCasePrompt
            }
            self.handler_mobile = {
                "functional": mobileFunctionalTestCasePrompt,
                "edge": mobileEdgeCaseTestCasePrompt,
                "integration": mobileIntegrationTestCasePrompt,
                "e2e": mobileE2eTestCasePrompt
            }
            self.handler_ios = {
                "functional": iosFunctionalTestCasePrompt,
                "edge": iosEdgeCaseTestCasePrompt,
                "integration": iosIntegrationTestCasePrompt,
                "e2e": iosE2eTestCasePrompt
            }
            
        self.handlers_generic_web = {
            "functional": GenericWebFunctionalTestCasePrompt,
            "edge": GenericWebEdgeCaseTestCasePrompt,
            "integration": GenericWebIntegrationTestCasePrompt,
            "e2e": GenericWebE2eTestCasePrompt
        }
        self.handler_generic_mobile = {
            "functional": GenericMobileFunctionalTestCasePrompt,
            "edge": GenericMobileEdgeCaseTestCasePrompt,
            "integration": GenericMobileIntegrationTestCasePrompt,
            "e2e": GenericMobileE2eTestCasePrompt
        }
        self.handler_generic_ios = {
            "functional": GenericIosFunctionalTestCasePrompt,
            "edge": GenericIosEdgeCaseTestCasePrompt,
            "integration": GenericIosIntegrationTestCasePrompt,
            "e2e": GenericIosE2eTestCasePrompt
        }

    def build_batch_prompt_web(self, batch, retrieved_content,is_image,image_content, is_file,file_content,is_video,end_to_end_flow,is_figma,all_flow_summary,image_chunks_figma,image_names,is_jira):
        handler = self.handlers_web[batch["test_type"]]

        numbered_scenarios = [
            f"{i+1:02d}. {scenario}"
            for i, scenario in enumerate(batch["scenarios"])
        ]

        scenario_text = "\n".join(numbered_scenarios)

        if is_image:
            system_prompt, user_prompt = handler(
            scenario_text,
            image_content,
            template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
        )
        elif is_file:
            system_prompt, user_prompt = handler(
            scenario_text,
            file_content,
            template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
        )
        elif is_video:
            system_prompt, user_prompt = handler(
            scenario_text,
            end_to_end_flow,
            template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
        )
        elif is_figma:
            system_prompt, user_prompt=handler(
               scenario_text,
               all_flow_summary,
               image_chunks_figma,
               image_names,
               template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,

            )        

        elif is_jira:
            system_prompt, user_prompt = handler(
                scenario_text,
                file_content,
                template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
            )

        else:
            system_prompt, user_prompt = handler(
                scenario_text,
                retrieved_content,
                template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
            )

        return {
            "test_type": batch["test_type"],
            "batch_number": batch["batch_number"],
            "system_prompt": system_prompt,
            "json_template": self.json_template,
            "user_prompt": user_prompt
        }
        
        
    def build_batch_prompt_mobile(self, batch, retrieved_content,is_image,image_content, is_file,file_content,is_video,end_to_end_flow,is_figma,all_flow_summary,image_chunks_figma,image_names,is_jira):
        handler = self.handler_mobile[batch["test_type"]]

        numbered_scenarios = [
            f"{i+1:02d}. {scenario}"
            for i, scenario in enumerate(batch["scenarios"])
        ]

        scenario_text = "\n".join(numbered_scenarios)

        if is_image:
            system_prompt, user_prompt = handler(
            scenario_text,
            image_content,
            template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
        )
            
        elif is_file:
            system_prompt, user_prompt = handler(
            scenario_text,
            file_content,
            template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
            )

        elif is_video:
            system_prompt, user_prompt = handler(
            scenario_text,
            end_to_end_flow,
            template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
            )

        elif is_jira:
            system_prompt, user_prompt = handler(
                scenario_text,
                file_content,
                template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
            )

        elif is_jira:
            system_prompt, user_prompt = handler(
                scenario_text,
                file_content,
                template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
            )

        elif is_figma:
            system_prompt, user_prompt=handler(
               scenario_text,
               all_flow_summary,
               image_chunks_figma,
               image_names,
               template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,

            )

        else:
            system_prompt, user_prompt = handler(
                scenario_text,
                retrieved_content,
                template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
            )

        return {
            "test_type": batch["test_type"],
            "batch_number": batch["batch_number"],
            "system_prompt": system_prompt,
            "json_template": self.json_template,
            "user_prompt": user_prompt
        }
    

    def build_batch_prompt_ios(self, batch, retrieved_content,image_content,is_image,file_content, is_file,end_to_end_flow,is_video,is_figma,is_jira,all_flow_summary,image_chunks_figma,image_names):
        handler = self.handler_ios[batch["test_type"]]

        numbered_scenarios = [
            f"{i+1:02d}. {scenario}"
            for i, scenario in enumerate(batch["scenarios"])
        ]

        scenario_text = "\n".join(numbered_scenarios)
        if is_video:
            system_prompt, user_prompt = handler(
                scenario_text,
                end_to_end_flow,
                template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
            )
        elif is_image:
            system_prompt, user_prompt = handler(
                scenario_text,
                image_content,
                template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
            )

        elif is_file:
            system_prompt, user_prompt = handler(
            scenario_text,
            file_content,
            template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
            )
        elif is_figma:
            system_prompt, user_prompt=handler(
               scenario_text,
               all_flow_summary,
               image_chunks_figma,
               image_names,
               template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,

            )
            

        elif is_jira:
            system_prompt, user_prompt = handler(
                scenario_text,
                file_content,
                template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
            )

        else:
            system_prompt, user_prompt = handler(
                scenario_text,
                retrieved_content,
                template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
            )

        return {
            "test_type": batch["test_type"],
            "batch_number": batch["batch_number"],
            "system_prompt": system_prompt,
            "json_template": self.json_template,
            "user_prompt": user_prompt
        }

    def build_batch_prompt_generic_web(self, batch):
        handler = self.handlers_generic_web[batch["test_type"]]

        numbered_scenarios = [
            f"{i+1:02d}. {scenario}"
            for i, scenario in enumerate(batch["scenarios"])
        ]

        scenario_text = "\n".join(numbered_scenarios)
        system_prompt, user_prompt = handler(
            scenario_text,
            template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
        )

        return {
            "test_type": batch["test_type"],
            "batch_number": batch["batch_number"],
            "system_prompt": system_prompt,
            "json_template": self.json_template,
            "user_prompt": user_prompt
        }

    def build_batch_prompt_generic_mobile(self, batch):
        handler = self.handler_generic_mobile[batch["test_type"]]

        numbered_scenarios = [
            f"{i+1:02d}. {scenario}"
            for i, scenario in enumerate(batch["scenarios"])
        ]

        scenario_text = "\n".join(numbered_scenarios)
        system_prompt, user_prompt = handler(
            scenario_text,
            template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
        )

        return {
            "test_type": batch["test_type"],
            "batch_number": batch["batch_number"],
            "system_prompt": system_prompt,
            "json_template": self.json_template,
            "user_prompt": user_prompt
        }

    def build_batch_prompt_generic_ios(self, batch):
        handler = self.handler_generic_ios[batch["test_type"]]

        numbered_scenarios = [
            f"{i+1:02d}. {scenario}"
            for i, scenario in enumerate(batch["scenarios"])
        ]

        scenario_text = "\n".join(numbered_scenarios)
        system_prompt, user_prompt = handler(
            scenario_text,
            template=None if self.service_provider in ["DefaultFireFlink", "Groq", "OpenAi"] else self.json_template,
        )

        return {
            "test_type": batch["test_type"],
            "batch_number": batch["batch_number"],
            "system_prompt": system_prompt,
            "json_template": self.json_template,
            "user_prompt": user_prompt
        }